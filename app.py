import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import pdfplumber
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

def extrair_dados_pdf_plumber(arquivo_pdf):
    if not chave: return {"erro": "Chave API não configurada."}, ""

    try:
        texto_completo = ""
        # Usa pdfplumber para extração robusta
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page in pdf.pages:
                texto_completo += page.extract_text() + "\n"
        
        if len(texto_completo) < 50:
             return {"erro": "O PDF parece vazio ou é uma imagem. Tente 'Imprimir como PDF' novamente."}, texto_completo

        nome_modelo = obter_modelo_disponivel()
        model = genai.GenerativeModel(nome_modelo)
        
        # PROMPT ESPECÍFICO PARA CM CAPITAL / FUTUROS
        prompt = f"""
        Você é um auditor contábil perito em B3.
        Analise o texto cru desta Nota de Corretagem (CM Capital/Sinacor):
        
        --- INÍCIO DO TEXTO ---
        {texto_completo[:15000]}
        --- FIM DO TEXTO ---
        
        Sua missão é calcular o RESULTADO LÍQUIDO DO DIA (Day Trade).
        
        Regras de Cálculo (Siga passo a passo):
        1. Identifique operações de Futuros (WDO/WIN).
        2. Para cada operação, ignore o preço de abertura. Olhe apenas os AJUSTES.
           - Valores com 'C' são Créditos (Positivos).
           - Valores com 'D' são Débitos (Negativos).
           - Exemplo: 317,87 C e 287,87 D resulta em (+317.87 - 287.87) = +30.00.
        3. Identifique os CUSTOS (Taxas B3 + Corretagem + ISS).
        4. O 'resultado_liquido_nota' deve ser: (Soma dos Ajustes) - (Total de Custos).
           - NÃO use o valor de "Valor dos Negócios" se estiver zerado.
           - NÃO use saldo de conta corrente.
        
        Retorne APENAS um JSON:
        {{
            "total_custos": "Valor total das taxas (float)",
            "irrf": "Valor do IRRF (float)",
            "resultado_liquido_nota": "Valor calculado do lucro/prejuízo liquido (float)",
            "data_pregao": "DD/MM/AAAA",
            "explicação": "Uma frase curta explicando a conta que você fez (ex: Ajuste 317C - 287D - taxas)"
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

aba1, aba2 = st.tabs(["🏋️‍♂️ Treino", "💰 Contador (PDF)"])

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
    st.header("Leitor Fiscal (PDF)")
    c1,c2 = st.columns(2)
    # Importante: seek(0) é feito internamente pelo pdfplumber, mas garantimos refresh
    pdf = c1.file_uploader("Nota PDF", type=["pdf"], key="pdf_up")
    prej = c2.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Extraindo dados com PDFPlumber..."):
            dados, texto_debug = extrair_dados_pdf_plumber(pdf)
        
        if "erro" in dados:
            st.error(f"Erro: {dados['erro']}")
            with st.expander("🛠️ Ver Texto Lido (Debug)"):
                st.text(texto_debug)
        else:
            liq = converter_para_float(dados.get('resultado_liquido_nota', 0))
            custos = converter_para_float(dados.get('total_custos', 0))
            irrf = converter_para_float(dados.get('irrf', 0))
            data = dados.get('data_pregao', '-')
            explicacao = dados.get('explicação', '-')
            
            st.success(f"Nota de {data}")
            st.info(f"🧠 **Raciocínio da IA:** {explicacao}")
            
            k1, k2, k3 = st.columns(3)
            cor = "normal" if liq >= 0 else "inverse"
            k1.metric("Líquido Calculado", f"R$ {liq:,.2f}", delta_color=cor)
            k2.metric("Custos", f"R$ {custos:,.2f}")
            k3.metric("IRRF", f"R$ {irrf:,.2f}")
            
            # Cálculo Imposto
            # Base = (Líquido + IRRF) - Prejuizo
            # (Porque o liquido já descontou taxas, mas o IRRF faz parte do lucro tributável antes de ser abatido no fim)
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

            with st.expander("🔍 Ver Texto Bruto da Nota"):
                st.text(texto_debug)
