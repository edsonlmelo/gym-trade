import streamlit as st
import pandas as pd
import google.generativeai as genai
import io

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="Gym Trade 🏋️‍♂️", layout="wide", page_icon="🏋️‍♂️")

# ==============================================================================
# ⚠️ COLOQUE SUA CHAVE AQUI ABAIXO
# ==============================================================================
# Busca a chave no cofre secreto do Streamlit Cloud
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    # Fallback para rodar local no seu PC se quiser
    GOOGLE_API_KEY = "AIzaSyCM1Xrw6zTKZ0nYwj_XOp8jTu3NdZkvbU0"

genai.configure(api_key=GOOGLE_API_KEY)

# --- FUNÇÕES ---
def obter_melhor_modelo():
    """
    Função inteligente que busca qual modelo está disponível na sua chave.
    Tenta pegar o mais recente (1.5) e, se não der, pega o padrão (pro).
    """
    try:
        # Lista todos os modelos disponíveis para sua chave
        modelos = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                modelos.append(m.name)
        
        # Tenta encontrar o Flash (mais rápido e barato)
        for m in modelos:
            if 'flash' in m and '1.5' in m: return m
        
        # Se não achar, tenta o Pro 1.5
        for m in modelos:
            if 'pro' in m and '1.5' in m: return m
            
        # Se não achar, pega qualquer um que tenha "gemini"
        for m in modelos:
            if 'gemini' in m: return m
            
        return 'gemini-pro' # Última tentativa
    except Exception as e:
        return 'gemini-1.5-flash' # Chute padrão se a listagem falhar

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
            st.error("Erro: Cabeçalho 'Ativo' não encontrado.")
            return None

        csv_limpo = '\n'.join(linhas[inicio_tabela:])
        df = pd.read_csv(io.StringIO(csv_limpo), sep=';', encoding='latin1')
        return df
    except Exception as e:
        st.error(f"Erro ao processar: {e}")
        return None

def analisar_com_gemini(resumo_texto):
    if "SUA_CHAVE_AQUI" in GOOGLE_API_KEY:
        return "⚠️ Configure sua API Key no código."
    
    # Busca o nome do modelo correto automaticamente
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
        return f"Erro na IA (Tentando usar {nome_modelo}): {e}"

# --- FRONTEND ---
st.title("🏋️‍♂️ Gym Trade")
st.markdown("### *Treino difícil, trade fácil.*")

st.sidebar.header("Check-in")
arquivo = st.sidebar.file_uploader("Relatório de Performance (.csv)", type=["csv"])

if arquivo:
    df = carregar_dados_blindado(arquivo)
    
    if df is not None:
        # Tenta achar a coluna de resultado
        cols = [c for c in df.columns if 'Res' in c and 'Op' in c]
        
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
                with st.spinner('Conectando ao cérebro do Coach...'):
                    resumo = f"Financeiro: R$ {total_resultado}. Trades: {qtd_trades}. Acerto: {taxa_acerto:.1f}%."
                    msg = analisar_com_gemini(resumo)
                    if total_resultado >= 0: st.success(f"🤖 **Coach:** {msg}")
                    else: st.error(f"🤖 **Coach:** {msg}")
            
            with st.expander("Ver Dados Brutos"):
                st.dataframe(df)
        else:
            st.error("Erro: Coluna de Resultado não encontrada.")