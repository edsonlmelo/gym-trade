import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import pypdf
import json
import re

# Configuração da Página
st.set_page_config(page_title="Gym Trade Pro", layout="wide", page_icon="📈")

# --- AUTENTICAÇÃO ---
try:
    chave = st.secrets["GOOGLE_API_KEY"]
except:
    chave = ""

if chave:
    genai.configure(api_key=chave)

# --- FUNÇÕES AUXILIARES ---

def obter_modelo_disponivel():
    """Busca automática do melhor modelo disponível na sua conta"""
    try:
        # Tenta listar modelos
        modelos = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Prioridade 1: Flash (Rápido)
        for m in modelos: 
            if 'flash' in m: return m
        # Prioridade 2: Pro (Robusto)
        for m in modelos: 
            if 'pro' in m: return m
            
        return 'models/gemini-1.5-flash' # Fallback
    except:
        return 'models/gemini-1.5-flash'

def converter_para_float(valor):
    """
    Transforma qualquer texto sujo (R$ 1.000,50 C) em número puro (1000.50).
    Resolve o erro ValueError.
    """
    if isinstance(valor, (int, float)):
        return float(valor)
    
    try:
        # Converte para string e padroniza
        texto = str(valor).strip().upper()
        
        # Remove caracteres financeiros e letras
        texto = texto.replace('R$', '').replace(' ', '')
        texto = texto.replace('C', '').replace('D', '')
        
        # Lógica para converter padrão BR (1.000,00) para US (1000.00)
        if ',' in texto:
            texto = texto.replace('.', '') # Remove ponto de milhar
            texto = texto.replace(',', '.') # Troca vírgula por ponto
            
        return float(texto)
    except:
        return 0.0

def limpar_json(texto):
    """Extrai apenas o JSON da resposta da IA"""
    try:
        padrao = r'\{.*\}'
        match = re.search(padrao, texto, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {"erro": "IA não retornou JSON válido."}
    except: 
        return {"erro": "Erro ao processar resposta da IA."}

def extrair_dados_pdf(arquivo_pdf):
    if not chave: return {"erro": "Chave API não configurada."}

    try:
        leitor = pypdf.PdfReader(arquivo_pdf)
        texto = ""
        for p in leitor.pages: texto += p.extract_text() + "\n"
        
        nome_modelo = obter_modelo_disponivel()
        model = genai.GenerativeModel(nome_modelo)
        
        # Prompt mais explícito para ajudar a IA
        prompt = f"""
        Analise esta Nota de Corretagem (B3/Sinacor).
        ---
        {texto[:15000]}
        ---
        Extraia os valores e retorne APENAS um JSON:
        {{
            "total_custos": "Soma de TODAS as taxas (Liquidação, Registro, Emolumentos, Corretagem, ISS). Ignore valores de operações.",
            "irrf": "Valor do I.R.R.F. s/ operações (Dedo-duro).",
            "resultado_liquido_nota": "Valor 'Líquido para [Data]'. Se for débito/negativo, use sinal de menos.",
            "data_pregao": "DD/MM/AAAA"
        }}
        """
        
        response = model.generate_content(prompt)
        return limpar_json(response.text)
    except Exception as e:
        return {"erro": str(e)}

def carregar_csv_blindado(uploaded_file):
    try:
        s = uploaded_file.getvalue().decode('latin1').split('\n')
        inicio = next((i for i, l in enumerate(s) if "Ativo" in l and ";" in l), 0)
        return pd.read_csv(io.StringIO('\n'.join(s[inicio:])), sep=';', encoding='latin1')
    except: return None

# --- INTERFACE ---
st.title("📈 Gym Trade Pro")

if not chave:
    st.error("⚠️ Chave API não configurada. Configure nos Secrets do Streamlit.")
    st.stop()

aba1, aba2 = st.tabs(["🏋️‍♂️ Treino (CSV)", "💰 Contador (PDF)"])

# --- ABA 1: CSV ---
with aba1:
    f = st.file_uploader("Relatório Profit (.csv)", type=["csv"])
    if f:
        df = carregar_csv_blindado(f)
        if df is not None:
            col = next((c for c in df.columns if ('Res' in c or 'Lucro' in c) and ('Op' in c or 'Liq' in c)), None)
            if col:
                # Usa a nova função segura aqui também
                df['V'] = df[col].apply(converter_para_float)
                res = df['V'].sum()
                trd = len(df)
                
                c1,c2 = st.columns(2)
                c1.metric("Resultado", f"R$ {res:,.2f}")
                c2.metric("Trades", trd)
                
                if st.button("Coach"):
                    nome = obter_modelo_disponivel()
                    msg = genai.GenerativeModel(nome).generate_content(f"Trader fez R$ {res:.2f} em {trd} trades. Feedback curto.").text
                    st.info(msg)
                st.dataframe(df)

# --- ABA 2: PDF ---
with aba2:
    st.header("Leitor Fiscal (IA)")
    c1,c2 = st.columns(2)
    pdf = c1.file_uploader("Nota PDF (Sem senha)", type=["pdf"])
    prej = c2.number_input("Prejuízo Anterior (R$)", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Auditando Nota..."):
            d = extrair_dados_pdf(pdf)
        
        if "erro" in d:
            st.error(f"Erro: {d['erro']}")
        else:
            # AQUI ESTAVA O ERRO! Agora usamos converter_para_float
            liq = converter_para_float(d.get('resultado_liquido_nota', 0))
            custos = converter_para_float(d.get('total_custos', 0))
            irrf = converter_para_float(d.get('irrf', 0))
            data = d.get('data_pregao', '-')
            
            st.success(f"Nota de {data}")
            k1, k2, k3 = st.columns(3)
            k1.metric("Líquido Nota", f"R$ {liq:,.2f}")
            k2.metric("Custos", f"R$ {custos:,.2f}")
            k3.metric("IRRF", f"R$ {irrf:,.2f}")
            
            # Cálculos
            # Se líquido é positivo, bruto é maior ainda (liq + custos + irrf)
            # Se líquido é negativo (prejuizo), bruto é menos negativo (liq + custos)
            # Simplificação: Bruto Aprox = Liquido da Nota + Custos Totais + IRRF Pago
            bruto_op = liq + custos + irrf
            
            # Base de Cálculo = (Bruto - Custos) - Prejuizo
            # Ou mais simples: (Liquido da Nota + IRRF) - Prejuizo
            base_calculo = (liq + irrf) - prej
            
            st.divider()
            if base_calculo > 0:
                imposto_devido = base_calculo * 0.20
                pagar = imposto_devido - irrf
                
                if pagar >= 10:
                    st.success(f"### 📄 DARF A PAGAR: R$ {pagar:,.2f}")
                    st.write(f"Base de Cálculo: R$ {base_calculo:,.2f}")
                elif pagar > 0:
                    st.info(f"### Acumular: R$ {pagar:,.2f}")
                    st.caption("DARF < R$ 10,00. Acumule para o próximo mês.")
                else:
                    st.success("### Isento")
                    st.caption("IRRF cobriu o imposto.")
            else:
                novo_prej = abs(base_calculo)
                st.error(f"### 📉 Prejuízo a Acumular: R$ {novo_prej:,.2f}")
