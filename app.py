import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import re
import time

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gym Trade Pro", layout="wide", page_icon="💎")

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

# --- MOTOR DE IA (LISTA DE ELITE) ---
def chamar_ia_elite(prompt, parts=None):
    if not chave: return {"erro": "API Key não configurada."}

    # SUA LISTA DE PREFERÊNCIA (Do melhor para o "backup")
    modelos_elite = [
        "models/gemini-2.0-flash",       # Sua preferência #1
        "models/gemini-2.0-flash-exp",   # Sua preferência #2
        "models/gemini-1.5-pro",         # Mais potente
        "models/gemini-1.5-flash"        # Último recurso
    ]

    erro_final = ""

    for modelo in modelos_elite:
        try:
            ia = genai.GenerativeModel(modelo)
            
            if parts:
                response = ia.generate_content([prompt, parts])
            else:
                response = ia.generate_content(prompt)
                
            # Se chegou aqui, funcionou! Retorna o texto e o modelo usado.
            return {"texto": response.text, "modelo": modelo}
            
        except Exception as e:
            # Se der erro (404, 429), guarda o erro e tenta o próximo da lista
            erro_final = str(e)
            continue
    
    # Se todos falharem
    return {"erro": f"Todos os modelos falharam. Último erro: {erro_final}"}

# --- COACH ---
def chamar_coach(texto_usuario):
    resultado = chamar_ia_elite(f"Aja como um Coach Trader experiente, curto e grosso. Analise: {texto_usuario}")
    
    if "erro" in resultado:
        return f"Erro no Coach: {resultado['erro']}"
    return resultado["texto"]

# --- LEITOR DE NOTA ---
@st.cache_data(show_spinner=False)
def ler_nota_corretagem(arquivo_bytes):
    part = {"mime_type": "application/pdf", "data": arquivo_bytes}

    prompt = """
    Analise a Nota de Corretagem (Brasil).
    
    EXTRAIA VALORES PARA IMPOSTO DE RENDA:
    
    1. "valor_negocios_explicito":
       - Procure: "Valor dos Negócios", "Total Líquido", "Ajuste Day Trade".
       - ATENÇÃO: Na CM Capital, pode estar solto no meio da página (ex: 30,00 C).
       - Se tiver 'C' = Positivo, 'D' = Negativo.
    
    2. "custos_totais":
       - Rodapé. Some TODAS as taxas: Liq + Reg + Emol + Corr + ISS.
    
    3. "irrf": Valor do I.R.R.F.
    
    4. "soma_creditos" e "soma_debitos":
       - Some ajustes C e D da tabela de negócios (Caso precise calcular).
    
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
    
    resultado = chamar_ia_elite(prompt, part)
    
    if "erro" in resultado:
        return {"erro": resultado["erro"]}
    
    dados = limpar_json(resultado["texto"])
    dados["modelo_usado"] = resultado.get("modelo", "Desconhecido")
    return dados

# --- INTERFACE ---
st.title("💎 Gym Trade Pro (Elite 2.0)")

if not chave:
    st.error("❌ Configure a API Key")
    st.stop()

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
                
                if st.button("🧠 Chamar Coach"):
                    with st.spinner("Analisando..."):
                        msg = chamar_coach(f"Fiz {formatar_real(total)} em {trades} operações.")
                        st.info(f"💡 {msg}")
                st.dataframe(df)
        except Exception as e: st.error(f"Erro CSV: {e}")

# ABA 2
with aba_contador:
    st.info("Prioridade de IA: Gemini 2.0 Flash > 1.5 Pro")
    pdf = st.file_uploader("Nota PDF", type=["pdf"])
    prejuizo = st.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
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
            
            # Lógica Híbrida: Prioriza valor explícito > cálculo
            if abs(vlr_negocios) > 0.01:
                bruto = vlr_negocios
                fonte = "Campo 'Valor dos Negócios'"
            else:
                bruto = abs(creditos) - abs(debitos)
                fonte = "Cálculo (C - D)"
            
            liq_op = bruto - abs(custos)
            base = liq_op - prejuizo
            
            st.success(f"Nota Processada: {data} (Usando {modelo})")
            
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
