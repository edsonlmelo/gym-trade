import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import re
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core.exceptions import ResourceExhausted, InternalServerError, ServiceUnavailable

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gym Trade Pro", layout="wide", page_icon="🛡️")

try:
    chave = st.secrets["GOOGLE_API_KEY"]
except:
    chave = ""

if chave:
    genai.configure(api_key=chave)

# --- FUNÇÕES ÚTEIS ---
def formatar_real(valor):
    if not isinstance(valor, (int, float)): return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

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

def limpar_json(texto):
    try:
        match = re.search(r'\{.*\}', texto, re.DOTALL)
        if match: return json.loads(match.group(0))
        return {"erro": "Erro no JSON retornado pela IA"}
    except: return {"erro": "Erro ao converter resposta para JSON"}

# --- MOTOR DE IA BLINDADO (RETRY AUTOMÁTICO) ---

# Esta função tenta até 5 vezes se der erro de Cota (429) ou Servidor (500)
# Espera: 2s, 4s, 8s, 16s... (Exponencial)
@retry(
    retry=retry_if_exception_type((ResourceExhausted, InternalServerError, ServiceUnavailable)),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    stop=stop_after_attempt(5)
)
def chamar_gemini_com_retry(modelo_nome, prompt, parts=None):
    model = genai.GenerativeModel(modelo_nome)
    if parts:
        response = model.generate_content([prompt, parts])
    else:
        response = model.generate_content(prompt)
    return response.text

def executar_ia_segura(prompt, parts=None):
    """
    Tenta o Gemini 2.0. Se der erro de NOME (404), tenta o 1.5.
    Se der erro de COTA (429), o @retry acima resolve.
    """
    if not chave: return {"erro": "Sem API Key"}

    # Lista de prioridade (Hardcoded para economizar cota de listagem)
    modelos = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    
    ultimo_erro = ""

    for modelo in modelos:
        try:
            texto_resp = chamar_gemini_com_retry(modelo, prompt, parts)
            return {"texto": texto_resp, "modelo": modelo}
        except Exception as e:
            # Se o erro for 429, o retry já tentou 5 vezes e falhou.
            # Se for 404 (Model not found), passamos para o próximo da lista.
            if "404" in str(e) or "not found" in str(e).lower():
                continue
            ultimo_erro = str(e)
            
    return {"erro": f"Falha após tentativas. Erro: {ultimo_erro}"}

# --- COACH ---
def chamar_coach(texto_usuario):
    resultado = executar_ia_segura(f"Aja como um Coach Trader experiente e direto. Resuma: {texto_usuario}")
    if "erro" in resultado:
        return f"Erro no Coach: {resultado['erro']}"
    return resultado["texto"]

# --- LEITOR DE NOTA (COM CACHE) ---
# Cache: Se você subir o mesmo PDF, ele não gasta cota de novo!
@st.cache_data(show_spinner=False) 
def ler_nota_corretagem(arquivo_bytes):
    part = {"mime_type": "application/pdf", "data": arquivo_bytes}

    prompt = """
    Analise a Nota de Corretagem (Brasil).
    
    EXTRAIA VALORES EXATOS PARA IR (DAY TRADE):
    
    1. "valor_negocios_explicito":
       - Procure campos: "Valor dos Negócios", "Total Líquido", "Ajuste Day Trade".
       - ATENÇÃO: Na CM Capital, procure no CORPO da nota (Ex: 30,00 C).
       - Na Clear/XP: Geralmente no cabeçalho ou resumo.
       - 'C' = Positivo, 'D' = Negativo.
    
    2. "custos_totais":
       - Vá ao rodapé. Some TODAS as taxas (Liq + Reg + Emol + Corr + ISS).
    
    3. "irrf": Valor do I.R.R.F.
    
    4. "soma_creditos" e "soma_debitos":
       - Some ajustes C e D da tabela de negócios (Plano B).
    
    Retorne JSON:
    {
        "valor_negocios_explicito": "0.00",
        "custos_totais": "0.00",
        "irrf": "0.00",
        "soma_creditos": "0.00",
        "soma_debitos": "0.00",
        "data": "DD/MM/AAAA",
        "corretora": "Nome"
    }
    """
    
    resultado = executar_ia_segura(prompt, part)
    
    if "erro" in resultado:
        return {"erro": resultado["erro"]}
    
    dados = limpar_json(resultado["texto"])
    dados["modelo_usado"] = resultado.get("modelo", "?")
    return dados

# --- INTERFACE ---
st.title("🛡️ Gym Trade Pro (Versão Blindada)")

aba_treino, aba_contador = st.tabs(["📊 Profit & Coach", "📝 Nota Fiscal"])

# ABA 1
with aba_treino:
    up = st.file_uploader("Relatório CSV", type=["csv"])
    if up:
        try:
            s = up.getvalue().decode('latin1').split('\n')
            i = next((x for x, l in enumerate(s) if "Ativo" in l and ";" in l), 0)
            df = pd.read_csv(io.StringIO('\n'.join(s[i:])), sep=';', encoding='latin1')
            
            col = next((c for c in df.columns if ('Res' in c or 'Lucro' in c) and ('Op' in c or 'Liq' in c)), None)
            
            if col:
                df['V'] = df[col].apply(converter_para_float)
                total = df['V'].sum()
                trades = len(df)
                
                c1, c2 = st.columns(2)
                c1.metric("Resultado", formatar_real(total))
                c2.metric("Trades", trades)
                
                if st.button("🧠 Coach"):
                    with st.spinner("Analisando (Pode demorar se a cota estiver cheia)..."):
                        msg = chamar_coach(f"Fiz {formatar_real(total)} em {trades} operações.")
                        if "Erro" in msg:
                            st.error(msg)
                        else:
                            st.info(f"💡 {msg}")
                st.dataframe(df)
        except Exception as e: st.error(f"Erro CSV: {e}")

# ABA 2
with aba_contador:
    st.info("Suporta: Clear, CM Capital (R$ 30,00 C), XP, etc.")
    pdf = st.file_uploader("Nota PDF", type=["pdf"])
    prejuizo = st.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Processando... (Se demorar, estou aguardando liberação do Google)"):
            d = ler_nota_corretagem(pdf.getvalue())
        
        if "erro" in d:
            st.error(f"❌ {d['erro']}")
        else:
            vlr_negocios = converter_para_float(d.get('valor_negocios_explicito', 0))
            creditos = converter_para_float(d.get('soma_creditos', 0))
            debitos = converter_para_float(d.get('soma_debitos', 0))
            custos = converter_para_float(d.get('custos_totais', 0))
            irrf = converter_para_float(d.get('irrf', 0))
            data = d.get('data', '-')
            modelo = d.get('modelo_usado', '?')
            
            # Lógica Híbrida: Prioriza valor explícito > cálculo
            if abs(vlr_negocios) > 0.01:
                bruto = vlr_negocios
                fonte = "Valor Explícito na Nota"
            else:
                bruto = abs(creditos) - abs(debitos)
                fonte = "Cálculo (C - D)"
            
            liq_op = bruto - abs(custos)
            base = liq_op - prejuizo
            
            st.success(f"Nota Processada: {data} (Via {modelo})")
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Bruto (Ajuste)", formatar_real(bruto), help=fonte)
            k2.metric("Custos", formatar_real(custos))
            k3.metric("Líquido Op.", formatar_real(liq_op))
            
            st.divider()
            
            if base > 0:
                imposto = base * 0.20
                darf = imposto - irrf
                if darf >= 10: st.success(f"### 🔥 DARF: {formatar_real(darf)}")
                elif darf > 0: st.warning(f"### Acumular: {formatar_real(darf)}")
                else: st.success("### Isento")
            else:
                st.error(f"### Prejuízo a Acumular: {formatar_real(abs(base))}")
