import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import re
import time

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gym Trade Pro", layout="wide", page_icon="🧩")

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

# --- CÉREBRO: ESCOLHA AUTOMÁTICA DE MODELO ---
@st.cache_resource
def selecionar_melhor_modelo():
    """
    Varre a conta do usuário e escolhe o melhor modelo disponível.
    Prioriza modelos 'latest' e 'flash' para evitar erro 404 e cotas baixas.
    """
    if not chave: return None
    
    try:
        # Pega a lista real do Google
        todos_modelos = list(genai.list_models())
        nomes = [m.name for m in todos_modelos if 'generateContent' in m.supported_generation_methods]
        
        # Ordem de preferência (do maior limite para o menor)
        preferencias = [
            "models/gemini-flash-latest",       # Geralmente limites altos
            "models/gemini-1.5-flash-latest",
            "models/gemini-1.5-flash",
            "models/gemini-1.5-flash-001",
            "models/gemini-2.0-flash",          # Bom, mas novo
            "models/gemini-2.0-flash-exp",
            "models/gemini-flash",              # Genérico
        ]
        
        # Tenta achar o preferido na lista do usuário
        for pref in preferencias:
            if pref in nomes:
                return pref
        
        # Se não achar nenhum específico, pega qualquer um que tenha 'flash'
        for nome in nomes:
            if 'flash' in nome:
                return nome
                
        # Se não tiver flash, pega o primeiro da lista (ex: pro)
        if nomes:
            return nomes[0]
            
        return None
    except Exception as e:
        return None

# --- COACH ---
def chamar_coach(texto_usuario):
    modelo_nome = selecionar_melhor_modelo()
    if not modelo_nome: return "Erro: Nenhum modelo de IA encontrado na sua conta."
    
    try:
        ia = genai.GenerativeModel(modelo_nome)
        resp = ia.generate_content(f"Aja como um Coach Trader experiente e breve. Analise: {texto_usuario}")
        return resp.text
    except Exception as e:
        if "429" in str(e): return "⏳ Cota excedida. Aguarde 1 min."
        return f"Erro técnico: {str(e)}"

# --- LEITOR DE NOTA ---
def ler_nota_corretagem(arquivo_pdf):
    modelo_nome = selecionar_melhor_modelo()
    if not modelo_nome: return {"erro": "Erro de conexão com Google AI (ListModels falhou)."}

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
           - Vá ao rodapé. Some TODAS as taxas (Liq + Reg + Emol + Corr + ISS).
        
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
        
        ia = genai.GenerativeModel(modelo_nome)
        resp = ia.generate_content([prompt, part])
        dados = limpar_json(resp.text)
        dados['modelo_usado'] = modelo_nome # Para sabermos qual ele escolheu
        return dados
        
    except Exception as e:
        if "429" in str(e): return {"erro": "⏳ Muitos pedidos seguidos. O Google bloqueou temporariamente. Espere 1 minuto."}
        return {"erro": f"Erro técnico ({modelo_nome}): {str(e)}"}

# --- INTERFACE ---
st.title("🎯 Gym Trade Pro")

# Mostra qual modelo foi escolhido automaticamente
modelo_ativo = selecionar_melhor_modelo()
if modelo_ativo:
    st.caption(f"✅ Conectado via: `{modelo_ativo}`")
else:
    st.error("❌ Erro: Não foi possível selecionar um modelo de IA.")

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
                        if "⏳" in msg: st.warning(msg)
                        elif "Erro" in msg: st.error(msg)
                        else: st.info(f"💡 {msg}")
                st.dataframe(df)
        except Exception as e: st.error(f"Erro CSV: {e}")

# ABA 2
with aba_contador:
    st.info("Leitor Universal Inteligente")
    pdf = st.file_uploader("Nota PDF", type=["pdf"])
    prejuizo = st.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Lendo Nota..."):
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
            modelo = d.get('modelo_usado', '?')
            
            # Prioridade: Valor Explícito > Cálculo
            if abs(vlr_negocios) > 0.01:
                bruto = vlr_negocios
                fonte = "Campo 'Valor dos Negócios'"
            else:
                bruto = abs(creditos) - abs(debitos)
                fonte = "Cálculo (C - D)"
            
            liq_op = bruto - abs(custos)
            base = liq_op - prejuizo
            
            st.success(f"Nota Processada: {data} (Via {modelo})")
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Bruto (Ajuste)", formatar_real(bruto))
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
