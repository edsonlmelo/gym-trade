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

# --- FORMATAÇÃO BRASIL ---
def formatar_real(valor):
    if not isinstance(valor, (int, float)): return "R$ 0,00"
    texto = f"R$ {valor:,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_json(texto):
    try:
        padrao = r'\{.*\}'
        match = re.search(padrao, texto, re.DOTALL)
        if match: return json.loads(match.group(0))
        return {"erro": "IA não retornou JSON válido."}
    except: return {"erro": "Erro ao processar JSON."}

def analisar_pdf_precisao(arquivo_pdf):
    if not chave: return {"erro": "Chave API não configurada."}

    # Modelos disponíveis
    candidatos = [
        "gemini-2.0-flash",
        "gemini-2.5-flash", 
        "models/gemini-2.0-flash",
        "gemini-1.5-flash"
    ]
    
    bytes_pdf = arquivo_pdf.getvalue()
    part_arquivo = {"mime_type": "application/pdf", "data": bytes_pdf}

    prompt = """
    Você é um Auditor Contábil. Analise esta Nota de Corretagem (Clear/CM/XP).
    
    SUA MISSÃO É APENAS EXTRAIR OS NÚMEROS. NÃO FAÇA CÁLCULOS.
    
    Extraia estes 3 valores exatos:
    
    1. "bruto_ajustes": 
       - Em notas CLEAR: Procure por "Ajuste day trade" ou "Total líquido". Se tiver 'C' é positivo.
       - Em notas CM/XP: É a soma dos ajustes 'C' menos ajustes 'D'.
       
    2. "total_custos":
       - Em notas CLEAR: Procure EXATAMENTE o campo "Total de despesas". Use esse valor.
       - Em outras: Soma de Taxas B3 + Corretagem + ISS.
       
    3. "irrf":
       - Valor do "IRRF Day Trade" ou "I.R.R.F. s/ operações".
    
    Retorne JSON:
    {
        "bruto_ajustes": 0.00,
        "total_custos": 0.00,
        "irrf": 0.00,
        "data_pregao": "DD/MM/AAAA",
        "modelo_usado": "Nome do modelo"
    }
    """

    for nome_modelo in candidatos:
        try:
            model = genai.GenerativeModel(nome_modelo)
            response = model.generate_content([prompt, part_arquivo])
            dados = limpar_json(response.text)
            
            if "erro" not in dados and dados.get('bruto_ajustes') != 0:
                dados['modelo_usado'] = nome_modelo
                return dados
        except:
            continue
    
    return {"erro": "Falha na leitura. Tente imprimir o PDF novamente."}

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
    st.error("Configure a API Key.")
    st.stop()

aba1, aba2 = st.tabs(["🏋️‍♂️ Treino", "💰 Contador (Python Precision)"])

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
                c1.metric("Resultado", formatar_real(res))
                c2.metric("Trades", trd)
                if st.button("Coach"):
                    try:
                        model = genai.GenerativeModel('gemini-2.0-flash')
                        msg = model.generate_content(f"Trader: {res}, {trd} trades. Dica curta.").text
                        st.info(msg)
                    except: pass
                st.dataframe(df)

with aba2:
    st.header("Leitor Fiscal de Precisão")
    st.caption("Cálculo tributário executado via Python (Zero Alucinação).")
    
    c1,c2 = st.columns(2)
    pdf = c1.file_uploader("Nota PDF", type=["pdf"], key="pdf_py")
    prej = c2.number_input("Prejuízo Anterior (R$)", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Extraindo dados brutos..."):
            dados = analisar_pdf_precisao(pdf)
        
        if "erro" in dados:
            st.error(f"Erro: {dados['erro']}")
        else:
            # EXTRAÇÃO DOS DADOS BRUTOS
            bruto = converter_para_float(dados.get('bruto_ajustes', 0))
            custos = converter_para_float(dados.get('total_custos', 0))
            irrf = converter_para_float(dados.get('irrf', 0))
            data = dados.get('data_pregao', '-')
            
            st.success(f"Nota Processada: {data}")
            
            # MOSTRA O QUE A IA LEU
            col1, col2, col3 = st.columns(3)
            col1.metric("Bruto (Ajustes)", formatar_real(bruto))
            col2.metric("Total Custos", formatar_real(custos))
            col3.metric("IRRF Retido", formatar_real(irrf))

            # --- CÁLCULO PYTHON (INFALÍVEL) ---
            # 1. Lucro Líquido Operacional (Base de Cálculo)
            base_calculo_op = bruto - custos
            
            # 2. Abatimento de Prejuízo
            base_final = base_calculo_op - prej
            
            st.divider()
            
            if base_final > 0:
                # 3. Imposto Devido (20%)
                imposto_devido = base_final * 0.20
                
                # 4. Valor Final a Pagar (Desconta o Dedo-duro)
                darf_pagar = imposto_devido - irrf
                
                # VISUALIZAÇÃO DA CONTA
                st.subheader("🧮 Memória de Cálculo Real")
                st.text(f"  {formatar_real(bruto)} (Bruto)")
                st.text(f"- {formatar_real(custos)} (Custos)")
                st.text(f"= {formatar_real(base_calculo_op)} (Lucro Líquido Operacional)")
                if prej > 0: st.text(f"- {formatar_real(prej)} (Prejuízo Anterior)")
                st.text(f"= {formatar_real(base_final)} (Base de Cálculo)")
                st.text(f"x 20% (Alíquota Day Trade)")
                st.text(f"= {formatar_real(imposto_devido)} (Imposto Devido)")
                st.text(f"- {formatar_real(irrf)} (IRRF já pago)")
                st.markdown(f"**= {formatar_real(darf_pagar)} (A PAGAR)**")
                
                if darf_pagar >= 10:
                    st.success(f"### ✅ GERAR DARF: {formatar_real(darf_pagar)}")
                elif darf_pagar > 0:
                    st.warning(f"### Acumular: {formatar_real(darf_pagar)}")
                    st.caption("Menor que R$ 10,00. Não pagar agora.")
                else:
                    st.success("### Isento (Saldo Credor)")
            
            else:
                st.error(f"### Prejuízo a Acumular: {formatar_real(abs(base_final))}")
