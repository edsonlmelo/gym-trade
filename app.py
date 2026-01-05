import streamlit as st
import pandas as pd
import google.generativeai as genai
import io

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="Gym Trade 🏋️‍♂️", layout="wide", page_icon="🏋️‍♂️")

# --- SEGURANÇA DA CHAVE (CLOUD vs LOCAL) ---
# Tenta pegar a chave do Cofre do Streamlit. 
# Se não achar (rodando local), avisa o usuário.
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    # Se quiser rodar no seu PC, troque a mensagem abaixo pela sua chave direta
    GOOGLE_API_KEY = "AIzaSyCXvrCGYRZNDlNXLySGzXkAljvGgln0umE" 

genai.configure(api_key=GOOGLE_API_KEY)

# --- FUNÇÕES ---
def obter_melhor_modelo():
    """Busca o melhor modelo disponível na chave (Flash ou Pro)"""
    try:
        modelos = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for m in modelos:
            if 'flash' in m and '1.5' in m: return m
        for m in modelos:
            if 'pro' in m and '1.5' in m: return m
        return 'gemini-1.5-flash'
    except:
        return 'gemini-1.5-flash'

def limpar_valor_monetario(valor):
    if isinstance(valor, (int, float)): return valor
    valor = str(valor).strip()
    valor = valor.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
    try: return float(valor)
    except: return 0.0

def carregar_dados_blindado(uploaded_file):
    try:
        string_data = uploaded_file.getvalue().decode('latin1')
        linhas = string_data.split('\n')
        inicio_tabela = -1
        for i, linha in enumerate(linhas):
            if "Ativo" in linha and ";" in linha:
                inicio_tabela = i
                break
        
        if inicio_tabela == -1:
            st.error("Erro: Cabeçalho 'Ativo' não encontrado no CSV.")
            return None

        csv_limpo = '\n'.join(linhas[inicio_tabela:])
        df = pd.read_csv(io.StringIO(csv_limpo), sep=';', encoding='latin1')
        return df
    except Exception as e:
        st.error(f"Erro ao processar: {e}")
        return None

def analisar_com_gemini(resumo_texto):
    # Verifica se a chave foi carregada corretamente
    if not GOOGLE_API_KEY or "SUA_CHAVE" in GOOGLE_API_KEY:
        return "⚠️ Erro de Segurança: Chave API não encontrada nos Segredos do Streamlit."
    
    nome_modelo = obter_melhor_modelo()
    try:
        model = genai.GenerativeModel(nome_modelo)
        prompt = f"""
        Atue como um Mentor de Day Trade experiente.
        Analise os dados de hoje:
        {resumo_texto}
        
        Regras:
        1. Feedback curto (máximo 3 linhas).
        2. Analise Risco x Retorno.
        3. Se fez mais de 15 trades, critique o overtrading.
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Erro na IA ({nome_modelo}): {e}"

# --- FRONTEND ---
st.title("🏋️‍♂️ Gym Trade")
st.markdown("### *Treino difícil, trade fácil.*")

# Verifica se a chave está configurada antes de começar
if not GOOGLE_API_KEY or "SUA_CHAVE" in GOOGLE_API_KEY:
    st.warning("⚠️ **Atenção:** A chave do Google não foi detectada.")
    st.info("Vá em **Manage App > Settings > Secrets** e adicione: `GOOGLE_API_KEY = 'sua-chave'`")

st.sidebar.header("Check-in")
arquivo = st.sidebar.file_uploader("Relatório de Performance (.csv)", type=["csv"])

if arquivo:
    df = carregar_dados_blindado(arquivo)
    
    if df is not None:
        # Busca colunas flexíveis (Res ou Resultado)
        cols = [c for c in df.columns if ('Res' in c or 'Lucro' in c) and ('Op' in c or 'Liq' in c)]
        
        if cols:
            col_resultado = cols[0]
            df['Resultado_Limpo'] = df[col_resultado].apply(limpar_valor_monetario)
            
            total_resultado = df['Resultado_Limpo'].sum()
            qtd_trades = len(df)
            trades_win = df[df['Resultado_Limpo'] > 0]
            taxa_acerto = (len(trades_win) / qtd_trades) * 100 if qtd_trades > 0 else 0
            
            cor = "normal" if total_resultado >= 0 else "off"

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Resultado", f"R$ {total_resultado:,.2f}", delta_color=cor)
            col2.metric("Trades", qtd_trades)
            col3.metric("Acerto", f"{taxa_acerto:.1f}%")
            
            pts = 0
            if total_resultado > 0: pts += 10
            if qtd_trades <= 10: pts += 10
            else: pts -= 5
            if taxa_acerto >= 60: pts += 10
            
            col4.metric("Score", f"{pts} pts")

            st.divider()
            if st.button("📢 Análise do Coach"):
                with st.spinner('Conectando ao Coach...'):
                    resumo = f"Financeiro: R$ {total_resultado}. Trades: {qtd_trades}. Acerto: {taxa_acerto:.1f}%."
                    msg = analisar_com_gemini(resumo)
                    if total_resultado >= 0: st.success(f"🤖 **Coach:** {msg}")
                    else: st.error(f"🤖 **Coach:** {msg}")
            
            with st.expander("Ver Dados Brutos"):
                st.dataframe(df)
        else:
            st.error("Erro: Coluna de Resultado não encontrada no arquivo.")
