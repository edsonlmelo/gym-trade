import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import pypdf
import json
import re

# Configuração da Página
st.set_page_config(page_title="Gym Trade Pro", layout="wide", page_icon="📈")

# --- AUTENTICAÇÃO E SEGURANÇA ---
try:
    chave = st.secrets["GOOGLE_API_KEY"]
except:
    chave = ""

# Configura a chave se ela existir
if chave:
    genai.configure(api_key=chave)

# --- FUNÇÕES ---

def limpar_json(texto):
    """
    Função cirúrgica para extrair JSON de respostas da IA.
    Usa Expressão Regular para achar o bloco { ... } ignorando textos extras.
    """
    try:
        # Procura pelo primeiro '{' e último '}'
        padrao = r'\{.*\}'
        match = re.search(padrao, texto, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
        else:
            return {"erro": "A IA respondeu, mas não gerou o formato JSON correto."}
    except Exception as e:
        return {"erro": f"Erro técnico ao processar resposta: {str(e)}"}

def extrair_dados_pdf(arquivo_pdf):
    """Lê o PDF e extrai dados financeiros"""
    if not chave:
        return {"erro": "Chave de API não configurada ou inválida."}

    try:
        leitor = pypdf.PdfReader(arquivo_pdf)
        texto_completo = ""
        for pagina in leitor.pages:
            texto_completo += pagina.extract_text() + "\n"
        
        # Modelo mais rápido e barato (Gratuito)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        Você é um auditor contábil. Analise o texto desta Nota de Corretagem (padrão Sinacor/CM Capital).
        
        TEXTO DA NOTA:
        ---
        {texto_completo[:15000]}
        ---
        
        Extraia os seguintes valores e retorne APENAS um objeto JSON.
        Se o valor for negativo na nota (ex: "D"), retorne negativo no JSON.
        
        Campos do JSON:
        1. "total_custos": Soma de TODAS as taxas operacionais (Taxa de liquidação + Taxa de Registro + Emolumentos + Corretagem + ISS/PIS/COFINS + Outras taxas). *Ignore o valor financeiro das operações, quero apenas os custos*.
        2. "irrf": Valor do I.R.R.F. s/ operações (Dedo-duro). Se não tiver, 0.0.
        3. "resultado_liquido_nota": O valor final "Líquido para [Data]" que aparece no resumo financeiro.
        4. "data_pregao": A data do pregão no formato DD/MM/AAAA.
        
        Responda APENAS o JSON.
        """
        
        response = model.generate_content(prompt)
        return limpar_json(response.text)
        
    except Exception as e:
        # Se o erro for de permissão, avisa claramente
        if "403" in str(e) or "PermissionDenied" in str(e):
             return {"erro": "ERRO DE PERMISSÃO: Sua API Key foi bloqueada ou é inválida. Gere uma nova no Google AI Studio."}
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

if not chave:
    st.error("🚨 **PARE TUDO:** A Chave de API não foi encontrada.")
    st.info("Vá em **Manage App > Settings > Secrets** e adicione: `GOOGLE_API_KEY = 'sua-chave-nova'`")
    st.stop() # Para a execução aqui se não tiver chave

aba_treino, aba_contador = st.tabs(["🏋️‍♂️ Treino (CSV)", "💰 Contador (PDF)"])

# --- ABA 1 ---
with aba_treino:
    st.caption("Importe o relatório de performance do Profit/Tryd")
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
                    try:
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        msg = model.generate_content(f"Trader fez R$ {res}, {trades} trades. Feedback curto e grosso.").text
                        st.info(f"🤖 **Coach:** {msg}")
                    except Exception as e:
                        if "PermissionDenied" in str(e):
                            st.error("❌ Erro de Permissão na API Key. Gere uma nova chave.")
                        else:
                            st.error(f"Erro: {e}")
                
                st.dataframe(df)

# --- ABA 2 ---
with aba_contador:
    st.header("Leitor de Nota (CM Capital / Sinacor)")
    st.caption("Suporta notas em PDF geradas pelo Home Broker.")
    
    c1, c2 = st.columns(2)
    pdf = c1.file_uploader("Upload da Nota (.pdf)", type=["pdf"])
    prejuizo = c2.number_input("Prejuízo Anterior a compensar", value=0.0, step=10.0)
    
    if pdf:
        with st.spinner("Auditando nota..."):
            dados = extrair_dados_pdf(pdf)
        
        if "erro" in dados:
            st.error(f"❌ Falha na leitura: {dados['erro']}")
        else:
            # Sucesso
            res_nota = float(dados.get('resultado_liquido_nota', 0))
            custos = float(dados.get('total_custos', 0))
            irrf = float(dados.get('irrf', 0))
            data = dados.get('data_pregao', 'N/A')
            
            st.success(f"✅ Nota processada com sucesso! Pregão: {data}")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Líquido da Nota", f"R$ {res_nota:,.2f}", help="Valor que efetivamente entrou/saiu da conta")
            col2.metric("Custos Totais", f"R$ {custos:,.2f}", delta_color="inverse", help="Corretagem + Taxas B3 + Impostos")
            col3.metric("IRRF (Dedo-Duro)", f"R$ {irrf:,.2f}", help="Já retido na fonte")
            
            # Cálculo Reverso para chegar no Bruto Operacional
            # Líquido Nota = (Bruto - Custos - IRRF)
            # Logo: Bruto = Líquido Nota + Custos + IRRF
            bruto_calculado = res_nota + custos + irrf
            
            # Base de Cálculo para DARF
            # Lucro Líquido Operacional (sem IRRF) = Bruto - Custos
            lucro_liquido_op = bruto_calculado - custos 
            base_calculo = lucro_liquido_op - prejuizo
            
            st.divider()
            st.subheader("🧮 Fechamento Fiscal")
            
            if base_calculo > 0:
                imposto = base_calculo * 0.20
                pagar = imposto - irrf
                
                # Regra dos 10 reais
                if pagar >= 10:
                    st.success(f"### 📄 DARF A PAGAR: R$ {pagar:,.2f}")
                    st.json({
                        "1. Lucro Líquido Operacional": lucro_liquido_op,
                        "2. (-) Prejuízo Anterior": prejuizo,
                        "3. (=) Base de Cálculo": base_calculo,
                        "4. (x) Alíquota 20%": imposto,
                        "5. (-) IRRF já pago": irrf,
                        "6. (=) Valor da DARF": pagar
                    })
                    st.warning("Vencimento: Último dia útil do mês seguinte ao da operação.")
                elif pagar > 0:
                    st.info(f"### Acumular: R$ {pagar:,.2f}")
                    st.caption("DARF menor que R$ 10,00 não se paga. Guarde esse valor para somar no mês que vem.")
                else:
                    st.success("### Isento (Saldo Zero)")
                    st.caption("O IRRF retido foi suficiente para cobrir o imposto devido.")
            else:
                novo_prejuizo = abs(base_calculo)
                st.error(f"### 📉 Prejuízo a Acumular: R$ {novo_prejuizo:,.2f}")
                st.markdown(f"**Importante:** Anote este valor de **R$ {novo_prejuizo:,.2f}**. No mês que vem, digite ele no campo 'Prejuízo Anterior' para não pagar imposto indevido.")
