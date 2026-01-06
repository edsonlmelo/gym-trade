import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import pypdf

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
    """Descobre qual modelo sua chave tem acesso para evitar erro 404"""
    try:
        modelos = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Tenta achar o Flash (mais rápido)
        for m in modelos:
            if 'flash' in m: return m
        # Tenta achar o Pro
        for m in modelos:
            if 'pro' in m: return m
        # Padrão seguro
        return 'gemini-1.5-flash'
    except:
        return 'gemini-1.5-flash'

def extrair_dados_pdf(arquivo_pdf):
    """Extrai texto do PDF e usa IA para identificar os valores financeiros"""
    try:
        leitor = pypdf.PdfReader(arquivo_pdf)
        texto_completo = ""
        for pagina in leitor.pages:
            texto_completo += pagina.extract_text()
        
        # Usa o modelo dinâmico
        nome_modelo = obter_modelo_disponivel()
        model = genai.GenerativeModel(nome_modelo)
        
        prompt = f"""
        Analise o texto desta Nota de Corretagem de Day Trade e extraia EXATAMENTE os valores abaixo em formato JSON.
        Se não encontrar, retorne 0.0.
        
        Texto da Nota:
        {texto_completo}
        
        Campos requeridos (retorne apenas números float, ponto como decimal):
        - "total_custos": (Soma de corretagem, emolumentos, taxas registro, ISS. Tudo que é custo).
        - "irrf": (Imposto de Renda Retido / Dedo-duro).
        - "resultado_liquido_nota": (O valor final creditado/debitado na conta).
        - "data_pregao": (Data formato DD/MM/AAAA).
        
        Retorne APENAS o JSON. Sem markdown.
        """
        response = model.generate_content(prompt)
        texto_limpo = response.text.replace('```json', '').replace('```', '').strip()
        return eval(texto_limpo)
        
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

aba_treino, aba_contador = st.tabs(["🏋️‍♂️ Treino Diário (CSV)", "💰 Contabilidade & DARF (PDF)"])

# --- ABA 1: O TREINO (CSV) ---
with aba_treino:
    st.header("Análise Técnica")
    arquivo_csv = st.file_uploader("Relatório de Performance (.csv)", type=["csv"], key="csv_uploader")
    
    if arquivo_csv:
        df = carregar_csv_blindado(arquivo_csv)
        if df is not None:
            # Tenta encontrar colunas de resultado
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
                
                # Feedback IA Rápido
                if st.button("Coach, analise meu dia"):
                    with st.spinner("Conectando ao Coach..."):
                        nome_modelo = obter_modelo_disponivel()
                        model = genai.GenerativeModel(nome_modelo)
                        try:
                            msg = model.generate_content(f"Trader fez R$ {res}, {trades} trades. Seja breve e duro sobre disciplina.").text
                            st.info(msg)
                        except Exception as e:
                            st.error(f"Erro na IA: {e}")
                    
                st.dataframe(df)
            else:
                st.warning("Não encontrei a coluna de Resultado no CSV. Verifique o arquivo.")

# --- ABA 2: O CONTADOR (PDF) ---
with aba_contador:
    st.header("Fechamento Fiscal")
    st.markdown("Suba sua **Nota de Corretagem (PDF)**.")
    
    col_input1, col_input2 = st.columns(2)
    arquivo_pdf = col_input1.file_uploader("Nota de Corretagem (.pdf)", type=["pdf"], key="pdf_uploader")
    prejuizo_anterior = col_input2.number_input("Prejuízo acumulado (Meses anteriores)", min_value=0.0, value=0.0, step=10.0)
    
    if arquivo_pdf:
        with st.spinner("Lendo nota..."):
            dados = extrair_dados_pdf(arquivo_pdf)
        
        if "erro" not in dados:
            st.success(f"Nota de {dados.get('data_pregao', 'Data não lida')}")
            
            resultado_nota = float(dados.get('resultado_liquido_nota', 0))
            custos_totais = float(dados.get('total_custos', 0))
            irrf = float(dados.get('irrf', 0))
            
            # Cálculo Reverso
            lucro_bruto_est = resultado_nota + custos_totais + irrf
            lucro_liq_op = lucro_bruto_est - custos_totais
            base_calculo = lucro_liq_op - prejuizo_anterior
            
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Resultado Nota", f"R$ {resultado_nota:,.2f}")
            c2.metric("Custos", f"R$ {custos_totais:,.2f}", delta_color="inverse")
            c3.metric("IRRF", f"R$ {irrf:,.2f}")
            c4.metric("Prejuízo Usado", f"- R$ {prejuizo_anterior:,.2f}")
            
            st.divider()
            
            if base_calculo > 0:
                imposto = base_calculo * 0.20
                darf = imposto - irrf
                if darf > 10:
                    st.success(f"### 📄 GERAR DARF: R$ {darf:,.2f}")
                    st.write("Vencimento: Último dia útil do mês seguinte.")
                elif darf > 0:
                    st.info(f"### Acumular: R$ {darf:,.2f}")
                    st.caption("DARF menor que R$ 10,00 não se paga. Acumule.")
                else:
                    st.success("### Isento (IRRF cobriu o imposto)")
            else:
                novo_prejuizo = abs(base_calculo)
                st.error(f"### 📉 Prejuízo a Declarar: R$ {novo_prejuizo:,.2f}")
        else:
            st.error(f"Erro ao ler nota: {dados['erro']}")
