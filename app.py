import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import re
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError
from google.api_core.exceptions import ResourceExhausted, InternalServerError, ServiceUnavailable

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gym Trade Pro", layout="wide", page_icon="🧘")

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
        return {"erro": "A IA não retornou os dados no formato correto."}
    except: return {"erro": "Erro ao converter resposta para JSON"}

# --- MOTOR DE IA (COM TRATAMENTO DE COTA) ---

@retry(
    retry=retry_if_exception_type((ResourceExhausted, InternalServerError, ServiceUnavailable)),
    wait=wait_exponential(multiplier=2, min=4, max=20), # Espera progressiva: 4s, 8s, 16s...
    stop=stop_after_attempt(3) # Tenta no máximo 3 vezes para não travar o app
)
def chamar_gemini_direto(prompt, parts=None):
    # Prioridade total ao 2.0 Flash como você pediu
    model = genai.GenerativeModel("models/gemini-2.0-flash") 
    if parts:
        response = model.generate_content([prompt, parts])
    else:
        response = model.generate_content(prompt)
    return response.text

def executar_ia_segura(prompt, parts=None):
    if not chave: return {"erro": "API Key não configurada."}

    try:
        texto_resp = chamar_gemini_direto(prompt, parts)
        return {"texto": texto_resp, "modelo": "Gemini 2.0 Flash"}
    
    except RetryError as e:
        # Captura o erro da biblioteca Tenacity (Esgotou tentativas)
        return {"erro": "🚦 Cota de IA excedida temporariamente. Aguarde 30 segundos e tente novamente."}
    except Exception as e:
        # Outros erros (404, etc)
        if "404" in str(e):
             # Fallback de emergência se o 2.0 sumir
             try:
                 model_bkp = genai.GenerativeModel("models/gemini-1.5-flash")
                 if parts: resp = model_bkp.generate_content([prompt, parts])
                 else: resp = model_bkp.generate_content(prompt)
                 return {"texto": resp.text, "modelo": "Gemini 1.5 Flash (Backup)"}
             except:
                 return {"erro": "Erro técnico 404: Modelo não encontrado na conta."}
        
        return {"erro": f"Erro técnico: {str(e)}"}

# --- COACH ---
def chamar_coach(texto_usuario):
    res = executar_ia_segura(f"Aja como um Coach Trader experiente e breve. Analise: {texto_usuario}")
    if "erro" in res:
        return f"⚠️ {res['erro']}"
    return res["texto"]

# --- LEITOR DE NOTA (CACHEADO) ---
@st.cache_data(show_spinner=False) 
def ler_nota_corretagem(arquivo_bytes):
    part = {"mime_type": "application/pdf", "data": arquivo_bytes}

    prompt = """
    Analise a Nota de Corretagem (Brasil).
    
    EXTRAIA VALORES EXATOS PARA IR (DAY TRADE):
    
    1. "valor_negocios_explicito":
       - Procure: "Valor dos Negócios", "Total Líquido", "Ajuste Day Trade".
       - ATENÇÃO: Na CM Capital, procure no CORPO/MEIO da nota (Ex: 30,00 C).
       - Na Clear/XP: Geralmente no topo.
       - 'C' = Positivo, 'D' = Negativo.
    
    2. "custos_totais":
       - Rodapé. Some TODAS as taxas: Taxa Operacional + Registro + Emolumentos + Corretagem + ISS.
    
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
st.title("🛡️ Gym Trade Pro")

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
                    with st.spinner("Analisando..."):
                        msg = chamar_coach(f"Fiz {formatar_real(total)} em {trades} operações.")
                        if "⚠️" in msg or "Erro" in msg:
                            st.warning(msg)
                        else:
                            st.info(f"💡 {msg}")
                st.dataframe(df)
        except Exception as e: st.error(f"Erro CSV: {e}")

# ABA 2
with aba_contador:
    st.info("Leitor Universal (Prioridade: Gemini 2.0)")
    pdf = st.file_uploader("Nota PDF", type=["pdf"])
    prejuizo = st.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
        # Verificamos cache para não gastar cota à toa
        with st.spinner("Processando Nota..."):
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
            
            # Lógica Híbrida Inteligente
            if abs(vlr_negocios) > 0.01:
                bruto = vlr_negocios
                fonte = "Campo 'Valor dos Negócios' (Nota)"
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
