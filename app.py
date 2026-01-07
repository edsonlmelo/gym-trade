import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import re
import time

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gym Trade Pro", layout="wide", page_icon="📡")

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

# --- MOTOR DE AUTO-DETECÇÃO (A SOLUÇÃO) ---
@st.cache_resource
def pegar_modelo_disponivel():
    """
    Pergunta ao Google quais modelos existem e pega o melhor Flash disponível.
    Evita erro 404 de nome incorreto.
    """
    if not chave: return None
    
    try:
        # 1. Lista todos os modelos da sua conta
        modelos_google = list(genai.list_models())
        nomes_disponiveis = [m.name for m in modelos_google if 'generateContent' in m.supported_generation_methods]
        
        # 2. Define a ordem de preferência (do mais moderno para o mais antigo)
        preferencias = [
            "gemini-2.0-flash",
            "gemini-2.0-flash-exp",
            "gemini-1.5-flash",
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash-001",
            "gemini-flash"
        ]
        
        # 3. Cruza as listas: Pega o primeiro da preferência que existe na sua conta
        for pref in preferencias:
            for real in nomes_disponiveis:
                if pref in real: # Se 'gemini-2.0-flash' estiver dentro de 'models/gemini-2.0-flash'
                    return real # Retorna o nome EXATO que o Google quer
        
        # 4. Se não achar nenhum Flash, pega o primeiro da lista geral
        if nomes_disponiveis:
            return nomes_disponiveis[0]
            
        return None
    except Exception as e:
        return None

# --- COACH ---
def chamar_coach(texto_usuario):
    modelo_nome = pegar_modelo_disponivel()
    if not modelo_nome: return "Erro: Nenhum modelo encontrado na conta."
    
    try:
        ia = genai.GenerativeModel(modelo_nome)
        resp = ia.generate_content(f"Aja como um Coach Trader experiente. Resuma: {texto_usuario}")
        return resp.text
    except Exception as e:
        if "429" in str(e): return "⏳ Cota cheia. Aguarde 1 min."
        return f"Erro técnico: {str(e)}"

# --- LEITOR DE NOTA ---
def ler_nota_corretagem(arquivo_pdf):
    modelo_nome = pegar_modelo_disponivel()
    if not modelo_nome: return {"erro": "Erro de conexão API (ListModels falhou)."}

    try:
        bytes_pdf = arquivo_pdf.getvalue()
        part = {"mime_type": "application/pdf", "data": bytes_pdf}

        prompt = """
        Analise a Nota de Corretagem (Brasil).
        
        EXTRAIA VALORES PARA IMPOSTO DE RENDA:
        
        1. "valor_negocios_explicito":
           - Busque: "Valor dos Negócios", "Total Líquido", "Ajuste Day Trade".
           - Na CM Capital, procure no CORPO da nota (Ex: 30,00 C).
           - Se tiver 'C' = Positivo, 'D' = Negativo.
        
        2. "custos_totais":
           - Rodapé. Some TODAS as taxas (Liq + Reg + Emol + Corr + ISS).
        
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
        
        ia = genai.GenerativeModel(modelo_nome)
        resp = ia.generate_content([prompt, part])
        return limpar_json(resp.text)
        
    except Exception as e:
        if "429" in str(e): return {"erro": "⏳ Muitos pedidos. Espere 1 minuto."}
        return {"erro": f"Erro ({modelo_nome}): {str(e)}"}

# --- INTERFACE ---
st.title("🎯 Gym Trade Pro")

# DIAGNÓSTICO VISUAL
modelo_ativo = pegar_modelo_disponivel()
if modelo_ativo:
    st.success(f"✅ Conectado via: `{modelo_ativo}`")
else:
    st.error("❌ Erro: Não foi possível listar modelos. Verifique a API Key.")

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
                        st.info(f"💡 {msg}")
                st.dataframe(df)
        except Exception as e: st.error(f"Erro CSV: {e}")

# ABA 2
with aba_contador:
    st.info("Leitor Universal (Auto-Detect)")
    pdf = st.file_uploader("Nota PDF", type=["pdf"])
    prejuizo = st.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Processando..."):
            d = ler_nota_corretagem(pdf)
        
        if "erro" in d:
            st.error(f"❌ {d['erro']}")
        else:
            vlr_negocios = converter_para_float(d.get('valor_negocios_explicito', 0))
            creditos = converter_para_float(d.get('soma_creditos', 0))
            debitos = converter_para_float(d.get('soma_debitos', 0))
            custos = converter_para_float(d.get('custos_totais', 0))
            irrf = converter_para_float(d.get('irrf', 0))
            data = d.get('data', '-')
            
            # Lógica Híbrida
            if abs(vlr_negocios) > 0.01:
                bruto = vlr_negocios
                fonte = "Valor Explícito na Nota"
            else:
                bruto = abs(creditos) - abs(debitos)
                fonte = "Cálculo (C - D)"
            
            liq_op = bruto - abs(custos)
            base = liq_op - prejuizo
            
            st.success(f"Nota Processada: {data}")
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Bruto", formatar_real(bruto), help=fonte)
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
