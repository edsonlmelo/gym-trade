import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import re

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gym Trade Pro", layout="wide", page_icon="🤖")

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
        return {"erro": "Erro no JSON"}
    except: return {"erro": "Erro JSON"}

# --- AUTO-DETECÇÃO DE MODELO (A SOLUÇÃO) ---
@st.cache_resource
def descobrir_modelo_ativo():
    """
    Pergunta para a API quais modelos estão disponíveis e escolhe o melhor.
    Evita erros de nome (404).
    """
    if not chave: return None
    
    try:
        # Lista tudo que a conta tem acesso
        modelos = list(genai.list_models())
        
        # Prioridade 1: Flash 2.0 ou 1.5 (Rápidos e Vision)
        for m in modelos:
            if 'flash' in m.name and 'generateContent' in m.supported_generation_methods:
                return m.name
        
        # Prioridade 2: Pro (Mais inteligentes)
        for m in modelos:
            if 'pro' in m.name and 'generateContent' in m.supported_generation_methods:
                return m.name
                
        # Fallback
        return 'models/gemini-1.5-flash'
    except Exception as e:
        return None

# --- COACH ---
def chamar_coach(texto_usuario):
    if not chave: return "Erro: API Key não configurada."
    
    nome_modelo = descobrir_modelo_ativo()
    if not nome_modelo: return "Erro: Nenhum modelo de IA encontrado na conta."

    try:
        ia = genai.GenerativeModel(nome_modelo)
        resp = ia.generate_content(f"Aja como um Coach Trader experiente e breve. Analise: {texto_usuario}")
        return resp.text
    except Exception as e:
        return f"Erro técnico no Coach: {str(e)}"

# --- LEITOR DE NOTA ---
def ler_nota_corretagem(arquivo_pdf):
    if not chave: return {"erro": "Sem API Key."}

    nome_modelo = descobrir_modelo_ativo()
    if not nome_modelo: return {"erro": "Não foi possível detectar um modelo de IA ativo na sua conta Google."}

    try:
        bytes_pdf = arquivo_pdf.getvalue()
        part = {"mime_type": "application/pdf", "data": bytes_pdf}

        prompt = """
        Analise esta Nota de Corretagem (Brasil).
        
        EXTRAIA VALORES PARA IMPOSTO DE RENDA:
        
        1. "valor_negocios_explicito":
           - Procure campos: "Valor dos Negócios", "Total Líquido", "Ajuste Day Trade".
           - Exemplo CM Capital: Pode estar no meio da nota (Ex: 30,00 C).
           - Exemplo Clear: Geralmente no topo.
           - Se 'C' = positivo, se 'D' = negativo.
        
        2. "custos_totais":
           - Some TODAS as taxas do rodapé (Liq + Reg + Emol + Corr + ISS).
        
        3. "irrf": Valor do I.R.R.F.
        
        4. "soma_creditos" e "soma_debitos":
           - Caso não ache valor explícito, some os ajustes C e D da tabela.
        
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
        
        ia = genai.GenerativeModel(nome_modelo)
        resp = ia.generate_content([prompt, part])
        return limpar_json(resp.text)
        
    except Exception as e:
        # AQUI ESTÁ A CORREÇÃO: Retorna o erro real para vermos
        return {"erro": f"Erro técnico ao ler PDF: {str(e)}"}

# --- INTERFACE ---
st.title("🎯 Gym Trade Pro")

# Mostra qual modelo foi detectado (DEBUG)
modelo_atual = descobrir_modelo_ativo()
if modelo_atual:
    st.caption(f"✅ Sistema conectado ao cérebro: `{modelo_atual}`")
else:
    st.error("❌ Erro grave: Não consegui listar modelos da sua conta Google.")

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
                    with st.spinner("Conectando..."):
                        msg = chamar_coach(f"Fiz {formatar_real(total)} em {trades} operações.")
                        if "Erro" in msg:
                            st.error(msg)
                        else:
                            st.info(f"💡 {msg}")
                st.dataframe(df)
        except Exception as e:
            st.error(f"Erro CSV: {e}")

# ABA 2
with aba_contador:
    st.info("Leitor Universal: Clear, CM, XP, Genial, BTG.")
    pdf = st.file_uploader("Nota PDF", type=["pdf"])
    prejuizo = st.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Lendo Nota..."):
            d = ler_nota_corretagem(pdf)
        
        if "erro" in d:
            # MOSTRA O ERRO REAL NA TELA
            st.error(f"❌ {d['erro']}")
            st.warning("Se o erro for '404', tente dar Reboot no App.")
        else:
            vlr_negocios = converter_para_float(d.get('valor_negocios_explicito', 0))
            creditos = converter_para_float(d.get('soma_creditos', 0))
            debitos = converter_para_float(d.get('soma_debitos', 0))
            custos = converter_para_float(d.get('custos_totais', 0))
            irrf = converter_para_float(d.get('irrf', 0))
            data = d.get('data', '-')
            corretora = d.get('corretora', '-')
            
            # Lógica Híbrida
            if abs(vlr_negocios) > 0.01:
                bruto = vlr_negocios
                fonte = "Campo 'Valor dos Negócios'"
            else:
                bruto = abs(creditos) - abs(debitos)
                fonte = "Cálculo (C - D)"
            
            liq_op = bruto - abs(custos)
            base = liq_op - prejuizo
            
            st.success(f"Nota Processada: {data} ({corretora})")
            st.caption(f"Fonte do dado: {fonte}")
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Bruto (Ajuste)", formatar_real(bruto))
            k2.metric("Custos", formatar_real(custos))
            k3.metric("Líquido Op.", formatar_real(liq_op))
            
            st.divider()
            
            if base > 0:
                imposto = base * 0.20
                darf = imposto - irrf
                
                if darf >= 10:
                    st.success(f"### 🔥 DARF: {formatar_real(darf)}")
                elif darf > 0:
                    st.warning(f"### Acumular: {formatar_real(darf)}")
                else:
                    st.success("### Isento")
            else:
                st.error(f"### Prejuízo a Acumular: {formatar_real(abs(base))}")
