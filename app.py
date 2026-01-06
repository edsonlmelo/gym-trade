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

# --- FUNÇÃO DE BUSCA DE MODELO (A SOLUÇÃO DO ERRO 404) ---
def obter_modelo_disponivel():
    """
    Lista os modelos disponíveis na sua conta e escolhe o melhor.
    Isso evita o erro '404 model not found'.
    """
    try:
        modelos_disponiveis = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                modelos_disponiveis.append(m.name)
        
        # 1. Tenta achar qualquer versão do Flash (Rápido e Gratuito)
        for m in modelos_disponiveis:
            if 'flash' in m: return m
            
        # 2. Se não achar, tenta o Pro (Mais inteligente)
        for m in modelos_disponiveis:
            if 'pro' in m: return m
            
        # 3. Se não achar, pega o primeiro da lista que seja Gemini
        if modelos_disponiveis:
            return modelos_disponiveis[0]
            
        return 'models/gemini-1.5-flash' # Chute final se a lista falhar
    except Exception as e:
        # Em caso de erro total na listagem, tenta o nome padrão
        return 'models/gemini-1.5-flash'

# --- FUNÇÕES AUXILIARES ---
def limpar_json(texto):
    try:
        padrao = r'\{.*\}'
        match = re.search(padrao, texto, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {"erro": "IA não retornou JSON válido."}
    except: return {"erro": "Erro ao converter resposta da IA."}

def extrair_dados_pdf(arquivo_pdf):
    if not chave: return {"erro": "Chave API não configurada."}

    try:
        leitor = pypdf.PdfReader(arquivo_pdf)
        texto = ""
        for p in leitor.pages: texto += p.extract_text() + "\n"
        
        # BUSCA O NOME CORRETO DO MODELO
        nome_modelo = obter_modelo_disponivel()
        model = genai.GenerativeModel(nome_modelo)
        
        prompt = f"""
        Você é um auditor. Analise esta Nota de Corretagem:
        ---
        {texto[:15000]}
        ---
        Retorne APENAS um JSON com:
        1. "total_custos": Soma de taxas (Liquidação + Registro + Emolumentos + Corretagem + Impostos). Ignore valor das operações.
        2. "irrf": Valor do I.R.R.F. s/ operações.
        3. "resultado_liquido_nota": O valor final líquido da nota.
        4. "data_pregao": DD/MM/AAAA.
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

def limpar_valor(v):
    if isinstance(v, (int, float)): return v
    return float(str(v).replace('R$','').replace(' ','').replace('.','').replace(',','.')) if v else 0.0

# --- INTERFACE ---
st.title("📈 Gym Trade Pro")

if not chave:
    st.error("Chave API não configurada nos Secrets.")
    st.stop()

aba1, aba2 = st.tabs(["🏋️‍♂️ Treino", "💰 Contador"])

with aba1:
    f = st.file_uploader("Relatório Profit (.csv)", type=["csv"])
    if f:
        df = carregar_csv_blindado(f)
        if df is not None:
            col = next((c for c in df.columns if 'Res' in c and 'Op' in c), None)
            if col:
                df['V'] = df[col].apply(limpar_valor)
                res = df['V'].sum()
                trd = len(df)
                
                c1,c2 = st.columns(2)
                c1.metric("Resultado", f"R$ {res:,.2f}")
                c2.metric("Trades", trd)
                
                if st.button("Coach"):
                    nome = obter_modelo_disponivel()
                    msg = genai.GenerativeModel(nome).generate_content(f"Trader fez R$ {res} em {trd} trades. Feedback curto.").text
                    st.info(msg)
                st.dataframe(df)

with aba2:
    st.header("Leitor de Nota (PDF)")
    c1,c2 = st.columns(2)
    pdf = c1.file_uploader("Nota PDF", type=["pdf"])
    prej = c2.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Auditando..."):
            d = extrair_dados_pdf(pdf)
        
        if "erro" in d:
            st.error(f"Erro: {d['erro']}")
        else:
            liq = float(d.get('resultado_liquido_nota', 0))
            custos = float(d.get('total_custos', 0))
            irrf = float(d.get('irrf', 0))
            data = d.get('data_pregao', '-')
            
            st.success(f"Nota de {data}")
            k1, k2, k3 = st.columns(3)
            k1.metric("Líquido Nota", f"R$ {liq:,.2f}")
            k2.metric("Custos", f"R$ {custos:,.2f}")
            k3.metric("IRRF", f"R$ {irrf:,.2f}")
            
            # Cálculo
            bruto = liq + custos + irrf
            base = (bruto - custos) - prej
            
            st.divider()
            if base > 0:
                darf = (base * 0.20) - irrf
                if darf >= 10: st.success(f"### PAGAR DARF: R$ {darf:,.2f}")
                elif darf > 0: st.info(f"Acumular: R$ {darf:,.2f}")
                else: st.success("Isento")
            else:
                st.error(f"Prejuízo a Acumular: R$ {abs(base):,.2f}")
