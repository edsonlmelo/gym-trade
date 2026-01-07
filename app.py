import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import pdfplumber
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

def extrair_texto_hibrido(arquivo_pdf):
    """
    Tenta ler com PDFPlumber. Se falhar, tenta com PyPDF.
    Garante que o texto seja extraído de qualquer jeito.
    """
    texto_final = ""
    metodo_usado = ""
    
    # TENTATIVA 1: PDFPlumber (Melhor para tabelas)
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page in pdf.pages:
                texto_final += page.extract_text() or ""
        metodo_usado = "PDFPlumber"
    except:
        pass
        
    # TENTATIVA 2: PyPDF (Melhor para texto cru) - Fallback
    if len(texto_final) < 50:
        try:
            # Reseta o ponteiro do arquivo para ler do zero
            arquivo_pdf.seek(0)
            leitor = pypdf.PdfReader(arquivo_pdf)
            texto_final = ""
            for page in leitor.pages:
                texto_final += page.extract_text() or ""
            metodo_usado = "PyPDF (Fallback)"
        except Exception as e:
            return "", f"Erro em ambos: {str(e)}"
            
    return texto_final, metodo_usado

def analisar_nota_ia(texto_completo):
    if not chave: return {"erro": "Chave API não configurada."}
    if len(texto_completo) < 50: return {"erro": "Não foi possível ler texto do PDF. O arquivo pode ser imagem."}

    try:
        nome_modelo = obter_modelo_disponivel()
        model = genai.GenerativeModel(nome_modelo)
        
        # PROMPT ESPECÍFICO PARA SUA NOTA (CM CAPITAL WDO)
        prompt = f"""
        Aja como um contador auditor. Analise o texto desta Nota de Corretagem (CM Capital):
        
        --- TEXTO DA NOTA ---
        {texto_completo[:15000]}
        --- FIM ---
        
        OBJETIVO: Calcular o Resultado Líquido do Pregão.
        
        INSTRUÇÕES DE RASTREIO:
        1. Procure pelas linhas que contêm "WDO" ou "WIN" (Futuros).
        2. Ao lado delas, procure valores com "C" (Crédito) ou "D" (Débito).
           - Exemplo no texto: "317,87 C" é lucro bruto. "287,87 D" é prejuízo bruto.
        3. Calcule o AJUSTE DO DIA: (Soma dos Créditos) - (Soma dos Débitos).
           - Ex: 317,87 - 287,87 = 30,00 Positivo.
        4. Identifique e some as TAXAS/CUSTOS (Taxa Liq, Registro, Emol, Corretagem, ISS).
        5. O Resultado Líquido Final é: (Ajuste do Dia) - (Total de Custos).
        
        Retorne JSON:
        {{
            "total_custos": "valor float",
            "irrf": "valor float (se houver)",
            "resultado_liquido_nota": "valor float (Ajuste - Custos)",
            "data_pregao": "DD/MM/AAAA",
            "logica_usada": "Explique quais valores C e D você encontrou e a conta feita."
        }}
        """
        
        response = model.generate_content(prompt)
        return limpar_json(response.text)
    except Exception as e:
        return {"erro": str(e)}

def converter_para_float(valor):
    if isinstance(valor, (int, float)): return float(valor)
    try:
        texto = str(valor).strip().upper()
        is_negative = 'D' in texto or '-' in texto
        texto = texto.replace('R$', '').replace(' ', '').replace('C', '').replace('D', '')
        if ',' in texto: texto = texto.replace('.', '').replace(',', '.')
        num = float(texto)
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

aba1, aba2 = st.tabs(["🏋️‍♂️ Treino", "💰 Contador Híbrido"])

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
    st.header("Leitor Fiscal (CM Capital)")
    c1,c2 = st.columns(2)
    pdf = c1.file_uploader("Nota PDF", type=["pdf"], key="pdf_hibrido")
    prej = c2.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Motor Híbrido lendo nota..."):
            # 1. Extrai Texto (Tenta Plumber -> Tenta PyPDF)
            texto_extraido, metodo = extrair_texto_hibrido(pdf)
            
            # 2. Envia para IA
            dados = analisar_nota_ia(texto_extraido)
        
        if "erro" in dados:
            st.error(f"Erro: {dados['erro']}")
            st.warning(f"Método tentado: {metodo}")
            with st.expander("Ver Texto Extraído (Debug)"):
                st.text(texto_extraido)
        else:
            liq = converter_para_float(dados.get('resultado_liquido_nota', 0))
            custos = converter_para_float(dados.get('total_custos', 0))
            irrf = converter_para_float(dados.get('irrf', 0))
            data = dados.get('data_pregao', '-')
            logica = dados.get('logica_usada', '-')
            
            st.success(f"Nota Processada ({metodo}) - Data: {data}")
            st.info(f"🧠 **Lógica da IA:** {logica}")
            
            k1, k2, k3 = st.columns(3)
            cor = "normal" if liq >= 0 else "inverse"
            k1.metric("Líquido Calculado", f"R$ {liq:,.2f}", delta_color=cor)
            k2.metric("Custos", f"R$ {custos:,.2f}")
            k3.metric("IRRF", f"R$ {irrf:,.2f}")
            
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
            
            with st.expander("Ver Texto Bruto"):
                st.text(texto_extraido)
