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

# --- FUNÇÕES ---

def obter_modelo_disponivel():
    """Busca o modelo disponível"""
    try:
        modelos = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for m in modelos: 
            if 'flash' in m: return m
        return 'models/gemini-1.5-flash'
    except:
        return 'models/gemini-1.5-flash'

def limpar_json(texto):
    try:
        padrao = r'\{.*\}'
        match = re.search(padrao, texto, re.DOTALL)
        if match: return json.loads(match.group(0))
        return {"erro": "IA não retornou JSON válido."}
    except: return {"erro": "Erro ao processar JSON."}

def extrair_dados_calculadora(arquivo_pdf):
    """
    Usa PyPDF (que funciona no seu arquivo) + Prompt de Cálculo Matemático.
    """
    if not chave: return {"erro": "Chave API não configurada."}, ""

    try:
        # Extração Simples e Direta
        leitor = pypdf.PdfReader(arquivo_pdf)
        texto_completo = ""
        for page in leitor.pages:
            texto_completo += page.extract_text() + "\n"
        
        # Verificação de Segurança
        if len(texto_completo) < 50:
             return {"erro": "O PDF parece ser uma imagem. O PyPDF não encontrou texto selecionável."}, texto_completo

        nome_modelo = obter_modelo_disponivel()
        model = genai.GenerativeModel(nome_modelo)
        
        # PROMPT "CALCULADORA DE AJUSTES"
        prompt = f"""
        Você é um auditor contábil. Analise o texto desta Nota de Corretagem (CM Capital - WDO):
        
        --- TEXTO DA NOTA ---
        {texto_completo[:15000]}
        --- FIM DO TEXTO ---
        
        O campo "Valor dos Negócios" costuma vir zerado nesta corretora. 
        VOCÊ DEVE CALCULAR O RESULTADO MANUALMENTE.
        
        Siga este roteiro de cálculo:
        1. Encontre as linhas de negociação (WDO/WIN).
        2. Identifique os AJUSTES DO DIA (Valores seguidos de C ou D).
           - Some todos os valores com 'C' (Crédito/Ganho).
           - Some todos os valores com 'D' (Débito/Perda).
           - Resultado Bruto = (Soma C) - (Soma D).
           - Exemplo: "317,87 C" e "287,87 D" -> Bruto = +30,00.
        3. Encontre e some os CUSTOS: (Taxa Liquidação + Registro + Emolumentos + Corretagem + ISS + Outras taxas).
        4. Resultado Líquido Final = (Resultado Bruto) - (Total Custos).
        
        Retorne JSON:
        {{
            "total_custos": "valor float",
            "irrf": "valor float (se houver)",
            "resultado_liquido_nota": "valor float (Resultado Líquido Final calculado)",
            "data_pregao": "DD/MM/AAAA",
            "memoria_calculo": "Descreva a conta: (Ajuste C - Ajuste D) - Custos"
        }}
        """
        
        response = model.generate_content(prompt)
        return limpar_json(response.text), texto_completo
        
    except Exception as e:
        return {"erro": str(e)}, ""

def converter_para_float(valor):
    if isinstance(valor, (int, float)): return float(valor)
    try:
        texto = str(valor).strip().upper()
        # Se a IA já mandou negativo no JSON, respeita.
        # Se mandou positivo mas com "D", inverte.
        is_negative = 'D' in texto or '-' in texto
        texto = texto.replace('R$', '').replace(' ', '').replace('C', '').replace('D', '')
        if ',' in texto: texto = texto.replace('.', '').replace(',', '.')
        num = float(texto)
        
        # Se o numero já é negativo (ex: -30.00), abs(num) tira o sinal.
        # Lógica: Se tem sinal de menos OU 'D', resultado final deve ser negativo.
        return -abs(num) if is_negative else abs(num)
    except: return 0.0

def carregar_csv_blindado(f):
    try:
        s = f.getvalue().decode('latin1').split('\n')
        i = next((x for x, l in enumerate(s) if "Ativo" in l and ";" in l), 0)
        return pd.read_csv(io.StringIO('\n'.join(s[i:])), sep=';', encoding='latin1')
    except: return None

# --- INTERFACE ---
st.title("📈 Gym Trade Pro")

if not chave:
    st.error("Chave API não configurada.")
    st.stop()

aba1, aba2 = st.tabs(["🏋️‍♂️ Treino", "💰 Contador"])

with aba1:
    f = st.file_uploader("CSV Profit", type=["csv"])
    if f:
        df = carregar_csv_blindado(f)
        if df is not None:
            col = next((c for c in df.columns if ('Res' in c or 'Lucro' in c) and ('Op' in c or 'Liq' in c)), None)
            if col:
                df['V'] = df[col].apply(converter_para_float)
                res = df['V'].sum()
                trd = len(df)
                c1,c2 = st.columns(2)
                c1.metric("Resultado", f"R$ {res:,.2f}")
                c2.metric("Trades", trd)
                if st.button("Coach"):
                    n = obter_modelo_disponivel()
                    msg = genai.GenerativeModel(n).generate_content(f"Trader: R$ {res:.2f}, {trd} trades. Feedback.").text
                    st.info(msg)
                st.dataframe(df)

with aba2:
    st.header("Leitor Fiscal (IA Calculadora)")
    st.info("Especializado em notas de Futuros (WDO/WIN) da CM Capital.")
    
    c1,c2 = st.columns(2)
    pdf = c1.file_uploader("Nota PDF", type=["pdf"], key="pdf_calc")
    prej = c2.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Lendo ajustes e calculando custos..."):
            dados, texto_debug = extrair_dados_calculadora(pdf)
        
        if "erro" in dados:
            st.error(f"Erro: {dados['erro']}")
            with st.expander("Ver Texto (Debug)"):
                st.text(texto_debug)
        else:
            liq = converter_para_float(dados.get('resultado_liquido_nota', 0))
            custos = converter_para_float(dados.get('total_custos', 0))
            irrf = converter_para_float(dados.get('irrf', 0))
            data = dados.get('data_pregao', '-')
            memoria = dados.get('memoria_calculo', '-')
            
            st.success(f"Nota Processada - Data: {data}")
            st.info(f"🧮 **Memória de Cálculo:** {memoria}")
            
            k1, k2, k3 = st.columns(3)
            cor = "normal" if liq >= 0 else "inverse"
            k1.metric("Líquido Calculado", f"R$ {liq:,.2f}", delta_color=cor)
            k2.metric("Custos", f"R$ {custos:,.2f}")
            k3.metric("IRRF", f"R$ {irrf:,.2f}")
            
            # Base = (Liquido + IRRF) - Prejuizo
            base_calculo = (liq + irrf) - prej
            
            st.divider()
            if base_calculo > 0:
                imposto = base_calculo * 0.20
                pagar = imposto - irrf
                if pagar >= 10: st.success(f"### PAGAR DARF: R$ {pagar:,.2f}")
                elif pagar > 0: st.warning(f"Acumular: R$ {pagar:,.2f}")
                else: st.success("Isento")
            else:
                st.error(f"Prejuízo a Acumular: R$ {abs(base_calculo):,.2f}")
            
            with st.expander("🔍 Ver Texto Bruto"):
                st.text(texto_debug)
