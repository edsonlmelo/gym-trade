import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
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
    # Para leitura de arquivos (Visão), o 1.5 Flash é mandatório
    return 'models/gemini-1.5-flash'

def limpar_json(texto):
    try:
        padrao = r'\{.*\}'
        match = re.search(padrao, texto, re.DOTALL)
        if match: return json.loads(match.group(0))
        return {"erro": "IA não retornou JSON válido."}
    except: return {"erro": "Erro ao processar JSON."}

def analisar_pdf_visao(arquivo_pdf):
    """
    ENVIA O ARQUIVO PDF DIRETO PARA A IA (VISÃO COMPUTACIONAL).
    Ignora problemas de fonte/texto do Python.
    """
    if not chave: return {"erro": "Chave API não configurada."}

    try:
        # Lê os bytes do arquivo
        bytes_pdf = arquivo_pdf.getvalue()
        
        # Prepara o blob para enviar ao Gemini
        part_arquivo = {
            "mime_type": "application/pdf",
            "data": bytes_pdf
        }

        nome_modelo = obter_modelo_disponivel()
        model = genai.GenerativeModel(nome_modelo)
        
        prompt = """
        Você é um Auditor Contábil Sênior. Estou te enviando um arquivo PDF de uma Nota de Corretagem (CM Capital).
        
        Sua tarefa é OLHAR para o documento e realizar a apuração fiscal do Day Trade (WDO/WIN).
        
        ATENÇÃO AOS DETALHES VISUAIS:
        1. Ignore o campo "Valor dos Negócios" se estiver zerado.
        2. Procure na tabela de negócios os valores de AJUSTE (Coluna "Valor Operação" ou "Ajuste").
           - Identifique visualmente a letra 'C' (Crédito/Positivo) ou 'D' (Débito/Negativo) ao lado dos números.
           - Exemplo visual: "317,87 C" conta como +317.87. "287,87 D" conta como -287.87.
           - FAÇA A CONTA: (Soma de todos os C) - (Soma de todos os D). Esse é o Bruto.
        3. Procure no rodapé o bloco de CUSTOS/DESPESAS (Taxa Liquidação, Registro, Emolumentos, Corretagem, ISS). Some todos.
        4. Resultado Líquido Final = (Resultado Bruto calculado) - (Total Custos).
        
        Retorne APENAS este JSON:
        {
            "total_custos": 0.00,
            "irrf": 0.00,
            "resultado_liquido_nota": 0.00,
            "data_pregao": "DD/MM/AAAA",
            "raciocinio": "Vi ajustes de X (C) e Y (D). A diferença é Z. Subtraí custos."
        }
        """
        
        # Envia Prompt + Arquivo
        response = model.generate_content([prompt, part_arquivo])
        return limpar_json(response.text)
        
    except Exception as e:
        return {"erro": f"Erro na Visão IA: {str(e)}"}

def converter_para_float(valor):
    if isinstance(valor, (int, float)): return float(valor)
    try:
        texto = str(valor).strip().upper()
        # Se a IA mandou negativo, mantém. Se mandou positivo com D, inverte.
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

aba1, aba2 = st.tabs(["🏋️‍♂️ Treino", "💰 Contador (Visão IA)"])

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
    st.header("Leitor Fiscal (Modo Visão)")
    st.info("A IA vai 'olhar' o PDF como uma imagem para ignorar erros de formatação.")
    
    c1,c2 = st.columns(2)
    pdf = c1.file_uploader("Nota PDF", type=["pdf"], key="pdf_vision")
    prej = c2.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("A IA está lendo o documento visualmente..."):
            dados = analisar_pdf_visao(pdf)
        
        if "erro" in dados:
            st.error(f"Erro: {dados['erro']}")
        else:
            liq = converter_para_float(dados.get('resultado_liquido_nota', 0))
            custos = converter_para_float(dados.get('total_custos', 0))
            irrf = converter_para_float(dados.get('irrf', 0))
            data = dados.get('data_pregao', '-')
            raciocinio = dados.get('raciocinio', '-')
            
            st.success(f"Nota de {data}")
            st.info(f"👀 **O que a IA viu:** {raciocinio}")
            
            # Edição Manual (Caso a IA erre por centavos)
            with st.expander("📝 Corrigir Valores Manualmente"):
                col_m1, col_m2, col_m3 = st.columns(3)
                liq = col_m1.number_input("Líquido Calculado", value=liq, step=1.0)
                custos = col_m2.number_input("Custos", value=custos, step=0.1)
                irrf = col_m3.number_input("IRRF", value=irrf, step=0.1)
            
            k1, k2, k3 = st.columns(3)
            cor = "normal" if liq >= 0 else "inverse"
            k1.metric("Líquido Final", f"R$ {liq:,.2f}", delta_color=cor)
            k2.metric("Custos", f"R$ {custos:,.2f}")
            k3.metric("IRRF", f"R$ {irrf:,.2f}")
            
            # Base = (Liquido + IRRF) - Prejuizo
            base_calculo = (liq + irrf) - prej
            
            st.divider()
            if base_calculo > 0:
                imposto = base_calculo * 0.20
                pagar = imposto - irrf
                if pagar >= 10: st.success(f"### PAGAR DARF: R$ {pagar:,.2f}")
                elif pagar > 0: st.warning(f"Acumular: R$ {pagar:,.2f}")
                else: st.success("Isento (IRRF cobriu)")
            else:
                st.error(f"Prejuízo a Acumular: R$ {abs(base_calculo):,.2f}")
