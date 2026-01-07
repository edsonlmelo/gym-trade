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

    # Lista de nomes para tentar (Força Bruta)
    # Tenta um por um até funcionar
    candidatos = [
        "gemini-1.5-flash",          # Nome padrão
        "gemini-1.5-flash-latest",   # Variação comum
        "gemini-1.5-flash-001",      # Versão específica
        "gemini-1.5-pro",            # Alternativa mais potente
        "gemini-1.5-pro-latest"
    ]
    
    bytes_pdf = arquivo_pdf.getvalue()
    part_arquivo = {"mime_type": "application/pdf", "data": bytes_pdf}

    prompt = """
    Você é um Auditor Contábil (B3). Analise visualmente esta Nota de Corretagem (PDF).
    
    MISSÃO: Calcular o Resultado Líquido de Day Trade (WDO/WIN).
    
    1. Ignore "Valor dos Negócios" se zerado.
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

    ultimo_erro = ""

    # LOOP DE TENTATIVAS
    for nome_modelo in candidatos:
        try:
            model = genai.GenerativeModel(nome_modelo)
            response = model.generate_content([prompt, part_arquivo])
            
            # Se chegou aqui, funcionou!
            dados = limpar_json(response.text)
            dados['modelo_sucesso'] = nome_modelo # Marca qual funcionou
            return dados
            
        except Exception as e:
            # Se der erro, guarda a mensagem e tenta o próximo da lista
            ultimo_erro = str(e)
            continue
    
    # Se sair do loop, todos falharam
    return {"erro": f"Todos os modelos falharam. Último erro: {ultimo_erro}"}

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

# CRIA 3 ABAS AGORA
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
                        # Tenta modelo padrão para texto
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        msg = model.generate_content(f"Trader: R$ {res:.2f}, {trd} trades. Feedback.").text
                        st.info(msg)
                    except:
                        st.error("Erro no Coach. Tente a aba Diagnóstico.")
                st.dataframe(df)

with aba2:
    st.header("Leitor Fiscal (Auto-Repair)")
    st.caption("O sistema tentará 5 modelos diferentes até conseguir ler sua nota.")
    
    c1,c2 = st.columns(2)
    pdf = c1.file_uploader("Nota PDF", type=["pdf"], key="pdf_brute")
    prej = c2.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Testando modelos de IA..."):
            dados = analisar_pdf_com_tentativas(pdf)
        
        if "erro" in dados:
            st.error(f"❌ Falha Total: {dados['erro']}")
            st.info("Vá na aba '🔧 Diagnóstico' para ver o que está acontecendo.")
        else:
            liq = converter_para_float(dados.get('resultado_liquido_nota', 0))
            custos = converter_para_float(dados.get('total_custos', 0))
            irrf = converter_para_float(dados.get('irrf', 0))
            data = dados.get('data_pregao', '-')
            raciocinio = dados.get('raciocinio', '-')
            modelo_ok = dados.get('modelo_sucesso', 'Desconhecido')
            
            st.success(f"✅ Nota Lida com Sucesso! (Usando: {modelo_ok})")
            st.info(f"🧠 **Raciocínio:** {raciocinio}")
            
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
    st.header("🔧 Diagnóstico de API")
    if st.button("Listar Modelos Disponíveis"):
        try:
            st.write("Consultando Google API...")
            modelos = []
            for m in genai.list_models():
                modelos.append(f"Nome: `{m.name}` | Métodos: {m.supported_generation_methods}")
            
            if modelos:
                st.success(f"Encontrados {len(modelos)} modelos disponíveis para sua chave:")
                for mod in modelos:
                    st.markdown(mod)
            else:
                st.warning("A API respondeu, mas a lista de modelos veio vazia.")
        except Exception as e:
            st.error(f"Erro ao conectar na API: {e}")
