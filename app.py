import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import re

# Configuração da Página
st.set_page_config(page_title="Gym Trade Pro", layout="wide", page_icon="🇧🇷")

# --- AUTENTICAÇÃO ---
try:
    chave = st.secrets["GOOGLE_API_KEY"]
except:
    chave = ""

if chave:
    genai.configure(api_key=chave)

# --- FUNÇÕES DE FORMATAÇÃO (BRASIL) ---

def formatar_real(valor):
    """
    Transforma 5278.50 em 'R$ 5.278,50' (Padrão Brasileiro)
    """
    if not isinstance(valor, (int, float)): return "R$ 0,00"
    # Formata como americano primeiro (1,000.00)
    texto = f"R$ {valor:,.2f}"
    # Troca os sinais: Vírgula vira X, Ponto vira Vírgula, X vira Ponto
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_json(texto):
    try:
        padrao = r'\{.*\}'
        match = re.search(padrao, texto, re.DOTALL)
        if match: return json.loads(match.group(0))
        return {"erro": "IA não retornou JSON válido."}
    except: return {"erro": "Erro ao processar JSON."}

def analisar_pdf_ptbr(arquivo_pdf):
    if not chave: return {"erro": "Chave API não configurada."}

    # Modelos modernos detectados na sua conta
    candidatos = [
        "gemini-2.0-flash",
        "gemini-2.5-flash", 
        "models/gemini-2.0-flash",
        "gemini-1.5-flash"
    ]
    
    bytes_pdf = arquivo_pdf.getvalue()
    part_arquivo = {"mime_type": "application/pdf", "data": bytes_pdf}

    prompt = """
    Você é um Auditor Contábil Brasileiro. Analise visualmente esta Nota de Corretagem.
    
    CALCULE O RESULTADO LÍQUIDO (DAY TRADE WDO/WIN).
    
    1. Ignore "Valor dos Negócios" se zerado.
    2. AJUSTES (Crédito vs Débito):
       - Identifique valores com 'C' (+) e 'D' (-).
       - Bruto = (Soma C) - (Soma D).
    3. CUSTOS:
       - Some Taxas B3 + Corretagem + ISS no rodapé.
    4. LÍQUIDO = Bruto - Custos.
    
    Retorne JSON:
    {
        "total_custos": 0.00,
        "irrf": 0.00,
        "resultado_liquido_nota": 0.00,
        "data_pregao": "DD/MM/AAAA",
        "raciocinio": "Explique a conta."
    }
    """

    for nome_modelo in candidatos:
        try:
            model = genai.GenerativeModel(nome_modelo)
            response = model.generate_content([prompt, part_arquivo])
            dados = limpar_json(response.text)
            if "erro" not in dados:
                dados['modelo_usado'] = nome_modelo
                return dados
        except:
            continue
    
    return {"erro": "Não foi possível ler a nota com nenhum modelo."}

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
    st.error("Configure a API Key nos Secrets.")
    st.stop()

aba1, aba2 = st.tabs(["🏋️‍♂️ Treino", "💰 Contador"])

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
                
                # Exibe formatado BR
                c1.metric("Resultado", formatar_real(res))
                c2.metric("Trades", trd)
                
                if st.button("Coach"):
                    try:
                        model = genai.GenerativeModel('gemini-2.0-flash')
                        msg = model.generate_content(f"Trader fez {formatar_real(res)} em {trd} trades. Feedback curto.").text
                        st.info(msg)
                    except: st.error("Erro Coach")
                st.dataframe(df)

with aba2:
    st.header("Leitor Fiscal (Padrão Brasil 🇧🇷)")
    
    c1,c2 = st.columns(2)
    pdf = c1.file_uploader("Nota PDF", type=["pdf"], key="pdf_br")
    prej = c2.number_input("Prejuízo Anterior (R$)", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Auditando..."):
            dados = analisar_pdf_ptbr(pdf)
        
        if "erro" in dados:
            st.error(f"Erro: {dados['erro']}")
        else:
            liq = converter_para_float(dados.get('resultado_liquido_nota', 0))
            custos = converter_para_float(dados.get('total_custos', 0))
            irrf = converter_para_float(dados.get('irrf', 0))
            data = dados.get('data_pregao', '-')
            
            st.success(f"Nota Processada: {data}")
            
            # Edição (Manual se precisar)
            with st.expander("📝 Conferência Manual"):
                col_m1, col_m2, col_m3 = st.columns(3)
                liq = col_m1.number_input("Líquido", value=liq, step=1.0, format="%.2f")
                custos = col_m2.number_input("Custos", value=custos, step=0.1, format="%.2f")
                irrf = col_m3.number_input("IRRF", value=irrf, step=0.1, format="%.2f")
            
            # Painel com formatação Brasileira
            k1, k2, k3 = st.columns(3)
            cor = "normal" if liq >= 0 else "inverse"
            k1.metric("Líquido Final", formatar_real(liq), delta_color=cor)
            k2.metric("Custos", formatar_real(custos))
            k3.metric("IRRF", formatar_real(irrf))
            
            base_calculo = (liq + irrf) - prej
            
            st.divider()
            if base_calculo > 0:
                imposto = base_calculo * 0.20
                pagar = imposto - irrf
                
                if pagar >= 10:
                    st.success(f"### 📄 DARF A PAGAR: {formatar_real(pagar)}")
                    st.write(f"Base de Cálculo: {formatar_real(base_calculo)}")
                elif pagar > 0:
                    st.warning(f"### Acumular: {formatar_real(pagar)}")
                    st.caption("Valor inferior a R$ 10,00. Pague apenas quando acumular.")
                else:
                    st.success("### Isento")
                    st.caption("IRRF cobriu o imposto.")
            else:
                st.error(f"### Prejuízo a Acumular: {formatar_real(abs(base_calculo))}")
