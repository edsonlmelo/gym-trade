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

# --- FUNÇÕES ---
def extrair_dados_pdf(arquivo_pdf):
    """Extrai texto do PDF e usa IA para identificar os valores financeiros"""
    try:
        # 1. Extrai texto bruto do PDF
        leitor = pypdf.PdfReader(arquivo_pdf)
        texto_completo = ""
        for pagina in leitor.pages:
            texto_completo += pagina.extract_text()
        
        # 2. Usa o Gemini para estruturar os dados (JSON)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        Analise o texto desta Nota de Corretagem de Day Trade e extraia EXATAMENTE os valores abaixo em formato JSON.
        Se não encontrar, retorne 0.0.
        
        Texto da Nota:
        {texto_completo}
        
        Campos requeridos (retorne apenas os números float, ponto como decimal):
        - "total_custos": (Soma de corretagem, emolumentos, taxas de registro, ISS, etc. TUDO que for custo operacional).
        - "irrf": (Imposto de Renda Retido na Fonte / Dedo-duro. Geralmente 1% sobre o lucro).
        - "resultado_liquido_nota": (O valor final creditado/debitado na conta).
        - "data_pregao": (Data da operação no formato DD/MM/AAAA).
        
        Retorne APENAS o JSON.
        """
        response = model.generate_content(prompt)
        # Limpeza básica para garantir que venha só o JSON
        texto_limpo = response.text.replace('```json', '').replace('```', '')
        return eval(texto_limpo) # Converte string JSON para dicionário Python
        
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

# Criamos Abas para organizar
aba_treino, aba_contador = st.tabs(["🏋️‍♂️ Treino Diário (CSV)", "💰 Contabilidade & DARF (PDF)"])

# --- ABA 1: O TREINO (CSV) ---
with aba_treino:
    st.header("Análise Técnica")
    arquivo_csv = st.file_uploader("Relatório de Performance (.csv)", type=["csv"], key="csv_uploader")
    
    if arquivo_csv:
        df = carregar_csv_blindado(arquivo_csv)
        if df is not None:
            col_res = next((c for c in df.columns if 'Res' in c and 'Op' in c), None)
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
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    msg = model.generate_content(f"Trader fez R$ {res}, {trades} trades. Seja breve e duro sobre disciplina.").text
                    st.info(msg)
                    
                st.dataframe(df)

# --- ABA 2: O CONTADOR (PDF) ---
with aba_contador:
    st.header("Fechamento Fiscal")
    st.markdown("Suba sua **Nota de Corretagem (PDF)** para calcular custos reais e IR.")
    
    col_input1, col_input2 = st.columns(2)
    arquivo_pdf = col_input1.file_uploader("Nota de Corretagem (.pdf)", type=["pdf"], key="pdf_uploader")
    prejuizo_anterior = col_input2.number_input("Prejuízo acumulado (Meses anteriores)", min_value=0.0, value=0.0, step=10.0)
    
    if arquivo_pdf:
        with st.spinner("O Contador IA está lendo a nota..."):
            dados = extrair_dados_pdf(arquivo_pdf)
        
        if "erro" not in dados:
            st.success(f"Nota lida com sucesso! Data: {dados.get('data_pregao', 'N/A')}")
            
            # --- CÁLCULOS FISCAIS ---
            resultado_nota = float(dados.get('resultado_liquido_nota', 0))
            custos_totais = float(dados.get('total_custos', 0))
            irrf = float(dados.get('irrf', 0))
            
            # Reconstruindo o Bruto aproximado (Liquido da nota + custos)
            # Nota: O cálculo exato depende se o resultado nota já desconta IRRF. 
            # Vamos assumir que Resultado Nota = (Bruto - Custos - IRRF)
            lucro_bruto_calculado = resultado_nota + custos_totais + irrf
            
            # Base de Cálculo Real
            lucro_liquido_operacional = lucro_bruto_calculado - custos_totais
            base_calculo = lucro_liquido_operacional - prejuizo_anterior
            
            # Painel Financeiro
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Resultado Nota (Líquido)", f"R$ {resultado_nota:,.2f}")
            c2.metric("Custos Totais", f"R$ {custos_totais:,.2f}", delta_color="inverse")
            c3.metric("IRRF (Já pago)", f"R$ {irrf:,.2f}")
            c4.metric("Prejuízo Compensado", f"- R$ {prejuizo_anterior:,.2f}")
            
            st.divider()
            
            # --- SITUAÇÃO FINAL ---
            if base_calculo > 0:
                imposto_devido = base_calculo * 0.20 # 20% Day Trade
                valor_darf = imposto_devido - irrf
                
                if valor_darf > 10: # DARF menor que 10 reais não se paga
                    st.success(f"### 📄 GERAR DARF: R$ {valor_darf:,.2f}")
                    st.write(f"**Memória de Cálculo:**")
                    st.write(f"(Lucro Líquido R$ {lucro_liquido_operacional:.2f} - Prejuízo R$ {prejuizo_anterior:.2f}) x 20% = Imposto R$ {imposto_devido:.2f}")
                    st.write(f"Imposto R$ {imposto_devido:.2f} - IRRF R$ {irrf:.2f} = **R$ {valor_darf:.2f}**")
                    st.warning("⚠️ Vencimento: Último dia útil do mês seguinte.")
                elif valor_darf > 0:
                    st.info(f"### Valor acumulado: R$ {valor_darf:,.2f}")
                    st.write("DARF menor que R$ 10,00 não é paga agora. Acumule para o próximo mês.")
                else:
                    st.success("### Isento: O IRRF cobriu o imposto devido.")
            else:
                novo_prejuizo = abs(base_calculo)
                st.error(f"### 📉 Prejuízo a Declarar: R$ {novo_prejuizo:,.2f}")
                st.write("Anote este valor! Você deve usá-lo no campo 'Prejuízo Acumulado' no próximo mês para abater lucros futuros.")
                
        else:
            st.error(f"Não consegui ler a nota. Erro: {dados['erro']}")
