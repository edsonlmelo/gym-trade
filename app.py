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

def limpar_json(texto):
    try:
        padrao = r'\{.*\}'
        match = re.search(padrao, texto, re.DOTALL)
        if match: return json.loads(match.group(0))
        return {"erro": "IA não retornou JSON válido."}
    except: return {"erro": "Erro ao processar JSON."}

def analisar_pdf_com_tentativas(arquivo_pdf):
    if not chave: return {"erro": "Chave API não configurada."}

    # LISTA ATUALIZADA COM BASE NO SEU DIAGNÓSTICO
    # Prioridade para o 2.0 Flash e 2.5 Flash que sua conta possui
    candidatos = [
        "gemini-2.0-flash",          # O mais estável para visão
        "gemini-2.5-flash",          # O mais novo
        "gemini-flash-latest",       # Genérico
        "models/gemini-2.0-flash",   # Variação com prefixo
        "models/gemini-2.5-flash"
    ]
    
    bytes_pdf = arquivo_pdf.getvalue()
    part_arquivo = {"mime_type": "application/pdf", "data": bytes_pdf}

    prompt = """
    Você é um Auditor Contábil (B3). Analise visualmente esta Nota de Corretagem (PDF).
    
    MISSÃO: Calcular o Resultado Líquido de Day Trade (WDO/WIN).
    
    1. Ignore "Valor dos Negócios" se estiver zerado.
    2. Identifique os AJUSTES na tabela de negócios:
       - Valores com 'C' são Créditos (+).
       - Valores com 'D' são Débitos (-).
       - Somatória Bruta = (Soma C) - (Soma D).
    3. Identifique e some os CUSTOS no rodapé (Taxas, Emolumentos, Corretagem, ISS).
    4. Líquido Final = Somatória Bruta - Custos Totais.
    
    Retorne JSON:
    {
        "modelo_usado": "Nome do modelo aqui",
        "total_custos": 0.00,
        "irrf": 0.00,
        "resultado_liquido_nota": 0.00,
        "data_pregao": "DD/MM/AAAA",
        "raciocinio": "Vi ajustes C e D. Diferença X. Menos custos Y."
    }
    """

    erros_log = []

    # LOOP DE TENTATIVAS
    for nome_modelo in candidatos:
        try:
            # Tenta criar o modelo
            model = genai.GenerativeModel(nome_modelo)
            # Tenta gerar o conteúdo
            response = model.generate_content([prompt, part_arquivo])
            
            # Se não der erro, processa o JSON
            dados = limpar_json(response.text)
            
            # Se o JSON vier com erro interno, considera falha e tenta o próximo
            if "erro" in dados:
                erros_log.append(f"{nome_modelo}: JSON inválido")
                continue

            dados['modelo_sucesso'] = nome_modelo 
            return dados
            
        except Exception as e:
            erros_log.append(f"{nome_modelo}: {str(e)}")
            continue
    
    # Se sair do loop, todos falharam
    return {"erro": f"Todos falharam. Logs: {'; '.join(erros_log)}"}

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

aba1, aba2, aba3 = st.tabs(["🏋️‍♂️ Treino", "💰 Contador", "🔧 Diagnóstico"])

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
                    try:
                        # Tenta usar o 2.0 Flash para o Coach também
                        model = genai.GenerativeModel('gemini-2.0-flash')
                        msg = model.generate_content(f"Trader: R$ {res:.2f}, {trd} trades. Feedback.").text
                        st.info(msg)
                    except:
                        st.error("Erro no Coach.")
                st.dataframe(df)

with aba2:
    st.header("Leitor Fiscal (Gemini 2.0/2.5)")
    st.caption("Usando modelos de última geração detectados na sua conta.")
    
    c1,c2 = st.columns(2)
    pdf = c1.file_uploader("Nota PDF", type=["pdf"], key="pdf_brute")
    prej = c2.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Analisando visualmente..."):
            dados = analisar_pdf_com_tentativas(pdf)
        
        if "erro" in dados:
            st.error(f"❌ Falha: {dados['erro']}")
        else:
            liq = converter_para_float(dados.get('resultado_liquido_nota', 0))
            custos = converter_para_float(dados.get('total_custos', 0))
            irrf = converter_para_float(dados.get('irrf', 0))
            data = dados.get('data_pregao', '-')
            raciocinio = dados.get('raciocinio', '-')
            modelo_ok = dados.get('modelo_sucesso', 'Desconhecido')
            
            st.success(f"✅ Nota Lida! (Modelo: {modelo_ok})")
            st.info(f"🧠 **Lógica:** {raciocinio}")
            
            # Edição
            with st.expander("📝 Ajuste Manual"):
                col_m1, col_m2, col_m3 = st.columns(3)
                liq = col_m1.number_input("Líquido", value=liq, step=1.0)
                custos = col_m2.number_input("Custos", value=custos, step=0.1)
                irrf = col_m3.number_input("IRRF", value=irrf, step=0.1)
            
            k1, k2, k3 = st.columns(3)
            cor = "normal" if liq >= 0 else "inverse"
            k1.metric("Líquido Final", f"R$ {liq:,.2f}", delta_color=cor)
            k2.metric("Custos", f"R$ {custos:,.2f}")
            k3.metric("IRRF", f"R$ {irrf:,.2f}")
            
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

with aba3:
    st.header("🔧 Diagnóstico")
    if st.button("Listar Modelos"):
        try:
            modelos = [m.name for m in genai.list_models()]
            st.write(modelos)
        except Exception as e:
            st.error(str(e))
