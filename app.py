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
    """Tenta usar o Flash (rápido), se não der, usa o Pro"""
    try:
        modelos = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for m in modelos: 
            if 'flash' in m: return m
        return 'models/gemini-1.5-flash'
    except:
        return 'models/gemini-1.5-flash'

def converter_para_float(valor):
    """Limpa texto financeiro (R$ 1.000,00 D -> -1000.00)"""
    if isinstance(valor, (int, float)): return float(valor)
    try:
        texto = str(valor).strip().upper()
        # Detecta se é negativo (D de Débito ou sinal de menos)
        is_negative = 'D' in texto or '-' in texto
        
        texto = texto.replace('R$', '').replace(' ', '').replace('C', '').replace('D', '')
        if ',' in texto:
            texto = texto.replace('.', '').replace(',', '.') # Padrão BR
            
        numero = float(texto)
        return -abs(numero) if is_negative else abs(numero)
    except:
        return 0.0

def limpar_json(texto):
    try:
        padrao = r'\{.*\}'
        match = re.search(padrao, texto, re.DOTALL)
        if match: return json.loads(match.group(0))
        return {"erro": "IA não retornou JSON válido."}
    except: return {"erro": "Erro ao processar JSON."}

def extrair_dados_pdf(arquivo_pdf):
    if not chave: return {"erro": "Chave API não configurada."}

    try:
        leitor = pypdf.PdfReader(arquivo_pdf)
        texto = ""
        for p in leitor.pages: texto += p.extract_text() + "\n"
        
        nome_modelo = obter_modelo_disponivel()
        model = genai.GenerativeModel(nome_modelo)
        
        # PROMPT REFORÇADO PARA CM CAPITAL / FUTUROS
        prompt = f"""
        Aja como um contador perito em Notas de Corretagem de Futuros (WDO/WIN).
        Analise o texto extraído desta nota (provável CM Capital):
        
        --- TEXTO DA NOTA ---
        {texto[:20000]}
        --- FIM DO TEXTO ---
        
        Sua missão é extrair os valores REAIS do dia, ignorando saldos anteriores.
        
        Raciocínio Obrigatório:
        1. Identifique os custos operacionais (Taxa Liquidação + Registro + Emolumentos + Corretagem + ISS). Some tudo em "total_custos".
        2. Identifique o IRRF (Imposto de Renda Retido / Dedo-duro).
        3. Para o "resultado_liquido_nota":
           - Em notas de WDO/WIN, procure o bloco "Resumo Financeiro" ou "Resumo dos Negócios".
           - O resultado do dia geralmente é a soma de "Ajuste de Posição" ou "Total Líquido".
           - IMPORTANTE: NÃO CONFUNDA COM "SALDO EM C/C" ou "TOTAL CONTA INVESTIMENTO". Quero apenas o resultado das operações DO DIA menos os custos.
           - Dica: Se houver operações de compra e venda com "Ajuste" (Ex: 317,87 C e 287,87 D), o bruto é a diferença (30,00 C). Subtraia os custos disso.
           - Se o valor tiver "D" é Débito (Negativo). Se tiver "C" é Crédito (Positivo).
        
        Retorne APENAS um JSON neste formato:
        {{
            "total_custos": "0.00",
            "irrf": "0.00",
            "resultado_liquido_nota": "0.00",
            "data_pregao": "DD/MM/AAAA",
            "raciocinio_ia": "Explique em 1 frase curta como chegou no valor liquido."
        }}
        """
        
        response = model.generate_content(prompt)
        return limpar_json(response.text)
    except Exception as e:
        return {"erro": str(e)}

def carregar_csv_blindado(f):
    try:
        s = f.getvalue().decode('latin1').split('\n')
        i = next((x for x, l in enumerate(s) if "Ativo" in l and ";" in l), 0)
        return pd.read_csv(io.StringIO('\n'.join(s[i:])), sep=';', encoding='latin1')
    except: return None

# --- INTERFACE ---
st.title("📈 Gym Trade Pro")

if not chave:
    st.error("Chave API ausente.")
    st.stop()

aba1, aba2 = st.tabs(["🏋️‍♂️ Treino", "💰 Contador Inteligente"])

# --- ABA 1 (Mantida igual) ---
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
                    msg = genai.GenerativeModel(n).generate_content(f"Trader: R$ {res} em {trd} trades. Feedback.").text
                    st.info(msg)
                st.dataframe(df)

# --- ABA 2 (Melhorada) ---
with aba2:
    st.header("Leitor de Nota (CM Capital / WDO)")
    c1,c2 = st.columns(2)
    pdf = c1.file_uploader("Nota PDF", type=["pdf"])
    prej = c2.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Contador IA analisando cada linha..."):
            d = extrair_dados_pdf(pdf)
        
        if "erro" in d:
            st.error(f"Erro: {d['erro']}")
        else:
            # Extração
            liq = converter_para_float(d.get('resultado_liquido_nota', 0))
            custos = converter_para_float(d.get('total_custos', 0))
            irrf = converter_para_float(d.get('irrf', 0))
            data = d.get('data_pregao', '-')
            raciocinio = d.get('raciocinio_ia', 'Sem explicação')
            
            st.success(f"Nota Processada! Data: {data}")
            
            # Mostra o raciocínio para validarmos
            with st.expander("🤖 Ver como a IA calculou (Clique aqui se o valor estiver estranho)"):
                st.write(f"**Explicação da IA:** {raciocinio}")
            
            # Cards
            k1, k2, k3 = st.columns(3)
            cor_liq = "normal" if liq >= 0 else "inverse"
            k1.metric("Líquido do Dia", f"R$ {liq:,.2f}", delta_color=cor_liq)
            k2.metric("Custos", f"R$ {custos:,.2f}")
            k3.metric("IRRF", f"R$ {irrf:,.2f}")
            
            # Lógica Fiscal (Dedo-duro já abate do imposto)
            # Bruto Operacional = Liquido + Custos + IRRF
            bruto = liq + custos + irrf
            
            # Base = (Bruto - Custos) - Prejuizo
            # Simplificando: (Liquido + IRRF) - Prejuizo
            base_calculo = (liq + irrf) - prej
            
            st.divider()
            st.subheader("🧮 Apuração de Imposto")
            
            if base_calculo > 0:
                imposto = base_calculo * 0.20
                pagar = imposto - irrf
                
                if pagar >= 10:
                    st.success(f"### 📄 DARF A PAGAR: R$ {pagar:,.2f}")
                    st.write(f"(Base R$ {base_calculo:.2f} x 20%) - IRRF R$ {irrf:.2f}")
                elif pagar > 0:
                    st.info(f"### Acumular: R$ {pagar:,.2f}")
                    st.caption("DARF < R$ 10,00. Não pague agora, acumule.")
                else:
                    st.success("### Isento (IRRF cobriu)")
            else:
                novo_prej = abs(base_calculo)
                st.error(f"### 📉 Prejuízo a Acumular: R$ {novo_prej:,.2f}")
                st.caption("Use este valor no campo 'Prejuízo Anterior' mês que vem.")
