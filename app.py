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
else:
    st.error("⚠️ Configure a GOOGLE_API_KEY nos Secrets!")

# --- FUNÇÕES INTELIGENTES ---
def obter_modelo_disponivel():
    """Tenta usar o Flash (rápido), se não der, usa o Pro"""
    try:
        modelos = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for m in modelos:
            if 'flash' in m: return m
        return 'gemini-1.5-flash'
    except:
        return 'gemini-1.5-flash'

def limpar_json(texto):
    """Remove caracteres estranhos que a IA coloca antes de converter"""
    try:
        # Encontra o primeiro '{' e o último '}'
        padrao = r'\{.*\}'
        match = re.search(padrao, texto, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
        else:
            return {"erro": "A IA não retornou um JSON válido."}
    except Exception as e:
        return {"erro": f"Erro ao processar JSON: {str(e)}"}

def extrair_dados_pdf(arquivo_pdf):
    """Lê o PDF e pede para a IA estruturar"""
    try:
        leitor = pypdf.PdfReader(arquivo_pdf)
        
        # Verifica se tem senha (criptografado)
        if leitor.is_encrypted:
            return {"erro": "O PDF tem senha. Desbloqueie o arquivo antes de enviar (Imprimir como PDF > Salvar)."}
            
        texto_completo = ""
        for pagina in leitor.pages:
            texto_extraido = pagina.extract_text()
            if texto_extraido:
                texto_completo += texto_extraido + "\n"
        
        # Verifica se conseguiu ler algo
        if not texto_completo.strip():
            return {"erro": "O PDF parece vazio ou é uma imagem escaneada. O sistema precisa de PDFs com texto selecionável.", "debug": "Sem texto"}

        # Chama a IA
        nome_modelo = obter_modelo_disponivel()
        model = genai.GenerativeModel(nome_modelo)
        
        prompt = f"""
        Aja como um contador experiente em B3. Analise o texto desta Nota de Corretagem:
        
        --- INÍCIO DA NOTA ---
        {texto_completo[:10000]} 
        --- FIM DA NOTA ---
        
        Extraia os valores e retorne APENAS um JSON (sem crases, sem markdown) com estas chaves:
        
        {{
            "total_custos": (Soma de: Taxa Liquidação + Taxa Registro + Emolumentos + Corretagem + ISS + Outros Custos. Retorne float. Ex: 15.50),
            "irrf": (Imposto de Renda Retido na Fonte, o 'dedo-duro'. Retorne float),
            "resultado_liquido_nota": (O valor final da nota, positivo ou negativo. Retorne float),
            "data_pregao": "DD/MM/AAAA"
        }}
        """
        
        response = model.generate_content(prompt)
        dados = limpar_json(response.text)
        
        # Adiciona o texto original para debug se precisar
        dados['debug_texto'] = texto_completo[:500] 
        return dados
        
    except Exception as e:
        return {"erro": str(e)}

def limpar_valor_monetario(valor):
    if isinstance(valor, (int, float)): return valor
    valor = str(valor).strip()
    valor = valor.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
    try: return float(valor)
    except: return 0.0

def carregar_csv_blindado(uploaded_file):
    try:
        string_data = uploaded_file.getvalue().decode('latin1')
        linhas = string_data.split('\n')
        inicio = next((i for i, l in enumerate(linhas) if "Ativo" in l and ";" in l), 0)
        return pd.read_csv(io.StringIO('\n'.join(linhas[inicio:])), sep=';', encoding='latin1')
    except: return None

# --- INTERFACE ---
st.title("📈 Gym Trade Pro")

aba_treino, aba_contador = st.tabs(["🏋️‍♂️ Treino (CSV)", "💰 Contador (PDF)"])

# --- ABA 1 ---
with aba_treino:
    arquivo_csv = st.file_uploader("Relatório de Performance (.csv)", type=["csv"], key="csv")
    if arquivo_csv:
        df = carregar_csv_blindado(arquivo_csv)
        if df is not None:
            col_res = next((c for c in df.columns if ('Res' in c or 'Lucro' in c) and ('Op' in c or 'Liq' in c)), None)
            if col_res:
                df['Valor'] = df[col_res].apply(limpar_valor_monetario)
                res = df['Valor'].sum()
                trades = len(df)
                acerto = (len(df[df['Valor']>0])/trades)*100 if trades > 0 else 0
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Resultado Bruto", f"R$ {res:,.2f}")
                c2.metric("Trades", trades)
                c3.metric("Acerto", f"{acerto:.1f}%")
                
                if st.button("Coach, analise"):
                    with st.spinner("Analisando..."):
                        nome = obter_modelo_disponivel()
                        msg = genai.GenerativeModel(nome).generate_content(f"Trader: R$ {res}, {trades} trades. Feedback curto.").text
                        st.info(msg)
                st.dataframe(df)

# --- ABA 2 ---
with aba_contador:
    st.header("Leitor de Nota de Corretagem")
    st.info("💡 Dica: O PDF não pode ter senha. Se tiver, use 'Imprimir como PDF' para remover a senha antes de subir.")
    
    c1, c2 = st.columns(2)
    pdf = c1.file_uploader("Upload da Nota (.pdf)", type=["pdf"])
    prejuizo = c2.number_input("Prejuízo Anterior", value=0.0, step=10.0)
    
    if pdf:
        with st.spinner("Lendo documento..."):
            dados = extrair_dados_pdf(pdf)
        
        if "erro" in dados:
            st.error(f"❌ Erro: {dados['erro']}")
            if "debug" in dados:
                st.warning("O sistema leu o arquivo mas não encontrou texto. É uma imagem?")
        else:
            # Sucesso
            res_nota = float(dados.get('resultado_liquido_nota', 0))
            custos = float(dados.get('total_custos', 0))
            irrf = float(dados.get('irrf', 0))
            data = dados.get('data_pregao', 'N/A')
            
            st.success(f"Nota processada! Data: {data}")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Líquido da Nota", f"R$ {res_nota:,.2f}")
            col2.metric("Custos Totais", f"R$ {custos:,.2f}")
            col3.metric("IRRF (Dedo-Duro)", f"R$ {irrf:,.2f}")
            
            # Cálculo DARF
            bruto_est = res_nota + custos + irrf
            liq_op = bruto_est - custos
            base = liq_op - prejuizo
            
            st.divider()
            st.subheader("🧮 Fechamento do Mês")
            
            if base > 0:
                imposto = base * 0.20
                pagar = imposto - irrf
                if pagar > 10:
                    st.success(f"### DARF A PAGAR: R$ {pagar:,.2f}")
                    st.json({"Lucro Op": liq_op, "Prejuízo Usado": prejuizo, "Imposto 20%": imposto, "IRRF Abatido": irrf})
                else:
                    st.info(f"Valor a pagar (R$ {pagar:.2f}) é menor que R$ 10. Acumule para o próximo mês.")
            else:
                st.error(f"### Prejuízo a Acumular: R$ {abs(base):,.2f}")
                st.caption("Você não paga nada e usa esse valor para abater lucros futuros.")
            
            with st.expander("Ver texto lido (Debug)"):
                st.text(dados.get('debug_texto', ''))
