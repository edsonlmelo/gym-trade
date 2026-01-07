import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gym Trade Pro", layout="wide", page_icon="🇧🇷")

# --- AUTENTICAÇÃO ---
try:
    chave = st.secrets["GOOGLE_API_KEY"]
except:
    chave = ""

if chave:
    genai.configure(api_key=chave)

# --- FUNÇÕES DE UTILIDADE ---

def formatar_real(valor):
    """Formata float para R$ 1.234,56"""
    if not isinstance(valor, (int, float)): return "R$ 0,00"
    texto = f"R$ {valor:,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")

def converter_para_float(valor):
    """Limpa strings sujas (R$ 1.000,00 D) para float (-1000.00)"""
    if isinstance(valor, (int, float)): return float(valor)
    try:
        texto = str(valor).strip().upper()
        is_negative = 'D' in texto or '-' in texto
        texto = texto.replace('R$', '').replace(' ', '').replace('C', '').replace('D', '')
        if ',' in texto: texto = texto.replace('.', '').replace(',', '.')
        num = float(texto)
        return -abs(num) if is_negative else abs(num)
    except: return 0.0

def limpar_json(texto):
    try:
        padrao = r'\{.*\}'
        match = re.search(padrao, texto, re.DOTALL)
        if match: return json.loads(match.group(0))
        return {"erro": "IA não retornou JSON válido."}
    except: return {"erro": "Erro ao processar JSON."}

def obter_modelo_seguro():
    """Retorna um modelo que sabemos que funciona na sua conta"""
    # Lista baseada no seu diagnóstico
    return [
        "gemini-2.0-flash", 
        "gemini-2.5-flash", 
        "models/gemini-2.0-flash",
        "gemini-1.5-flash"
    ]

# --- FUNÇÃO DO COACH (CORRIGIDA) ---
def chamar_coach(resumo_texto):
    if not chave: return "Erro: Chave API não configurada."
    
    candidatos = obter_modelo_seguro()
    
    for nome_modelo in candidatos:
        try:
            model = genai.GenerativeModel(nome_modelo)
            response = model.generate_content(resumo_texto)
            return response.text
        except:
            continue
            
    return "O Coach está indisponível no momento (Erro de API)."

# --- FUNÇÃO DO LEITOR UNIVERSAL (PDF) ---
def analisar_pdf_universal(arquivo_pdf):
    if not chave: return {"erro": "Chave API não configurada."}

    bytes_pdf = arquivo_pdf.getvalue()
    part_arquivo = {"mime_type": "application/pdf", "data": bytes_pdf}

    # PROMPT HÍBRIDO: Atende CLEAR (Explícito) e CM (Cálculo)
    prompt = """
    Você é um Auditor Contábil Sênior. Analise visualmente esta Nota de Corretagem.
    
    EXTRAIA OS VALORES PARA APURAÇÃO DE DAY TRADE (WDO/WIN).
    
    1. CUSTOS TOTAIS:
       - Some TODAS as despesas no rodapé: Taxa Operacional/Liquidação + Registro + Emolumentos + Corretagem + ISS/PIS/COFINS.
       
    2. IRRF:
       - Valor do "I.R.R.F. s/ operações" ou "IRRF Day Trade".
       
    3. RESULTADO BRUTO (Busque de duas formas):
       - FORMA A (Explícita): Procure por um campo final chamado "Total Líquido", "Ajuste Day Trade" ou "Total Nota".
       - FORMA B (Cálculo de Ajustes): Olhe a tabela de negócios. Some os valores 'C' (Crédito) e subtraia os valores 'D' (Débito).
         Ex: 317,87 C e 287,87 D = (317.87 - 287.87) = 30.00.
    
    Retorne JSON:
    {
        "custos_totais": 0.00,
        "irrf": 0.00,
        "bruto_explicito": 0.00,
        "bruto_calculado_ajustes": 0.00,
        "data_pregao": "DD/MM/AAAA",
        "modelo_usado": "Nome do modelo"
    }
    """

    candidatos = obter_modelo_seguro()

    for nome_modelo in candidatos:
        try:
            model = genai.GenerativeModel(nome_modelo)
            response = model.generate_content([prompt, part_arquivo])
            dados = limpar_json(response.text)
            
            if "erro" not in dados:
                dados['modelo_usado'] = nome_modelo
                return dados
        except:
            continue
    
    return {"erro": "Não foi possível ler a nota. Tente imprimir o PDF novamente."}

def carregar_csv_blindado(f):
    try:
        s = f.getvalue().decode('latin1').split('\n')
        i = next((x for x, l in enumerate(s) if "Ativo" in l and ";" in l), 0)
        return pd.read_csv(io.StringIO('\n'.join(s[i:])), sep=';', encoding='latin1')
    except: return None

# --- INTERFACE ---
st.title("📈 Gym Trade Pro")

if not chave:
    st.error("⚠️ API Key não encontrada.")
    st.stop()

aba1, aba2 = st.tabs(["🏋️‍♂️ Treino (CSV)", "💰 Contador Universal (PDF)"])

# --- ABA 1: COACH E TREINO ---
with aba1:
    f = st.file_uploader("Relatório Profit (.csv)", type=["csv"])
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
                
                # BOTÃO COACH RESTAURADO
                if st.button("📢 Coach, analise meu dia"):
                    with st.spinner("O Coach está pensando..."):
                        prompt_coach = f"Atue como um mentor de trading duro. O aluno fez {formatar_real(res)} em {trd} operações hoje. Dê um feedback de 2 linhas sobre disciplina e risco."
                        msg = chamar_coach(prompt_coach)
                        st.info(f"🤖 **Coach:** {msg}")
                
                st.dataframe(df)

# --- ABA 2: CONTADOR UNIVERSAL ---
with aba2:
    st.header("Leitor Fiscal Universal 🇧🇷")
    st.caption("Compatível com Clear, CM Capital, XP, Genial, BTG, etc.")
    
    c1,c2 = st.columns(2)
    pdf = c1.file_uploader("Nota de Corretagem (PDF)", type=["pdf"], key="pdf_universal")
    prej = c2.number_input("Prejuízo Anterior (R$)", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Auditando Nota..."):
            dados = analisar_pdf_universal(pdf)
        
        if "erro" in dados:
            st.error(f"Erro: {dados['erro']}")
        else:
            # EXTRAÇÃO
            custos = converter_para_float(dados.get('custos_totais', 0))
            irrf = converter_para_float(dados.get('irrf', 0))
            bruto_explicito = converter_para_float(dados.get('bruto_explicito', 0))
            bruto_calc = converter_para_float(dados.get('bruto_calculado_ajustes', 0))
            data = dados.get('data_pregao', '-')
            
            # --- LÓGICA DE DECISÃO PYTHON (O PULO DO GATO) ---
            # Se tiver valor explícito (Clear), usa. Se for zero (CM), usa o calculado.
            # Também protegemos contra valores absurdos.
            if abs(bruto_explicito) > 0.01:
                bruto_final = bruto_explicito
                metodo = "Valor da Nota (Explícito)"
            else:
                bruto_final = bruto_calc
                metodo = "Cálculo de Ajustes (C - D)"
            
            st.success(f"Nota Processada: {data}")
            
            # Mostra os dados brutos para transparência
            with st.expander(f"Detalhes da Leitura ({metodo})"):
                st.write(f"Bruto Lido na Nota: {formatar_real(bruto_explicito)}")
                st.write(f"Bruto Calculado (C-D): {formatar_real(bruto_calc)}")
                st.write(f"Custos Identificados: {formatar_real(custos)}")
            
            # --- CÁLCULO TRIBUTÁRIO ---
            # Base = (Bruto - Custos) - Prejuizo
            # Nota: O Bruto aqui já é o ajuste financeiro, então subtraímos custos para ter o líquido.
            lucro_liquido_op = bruto_final - custos
            base_calculo = lucro_liquido_op - prej
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Resultado Bruto", formatar_real(bruto_final), help=metodo)
            col2.metric("Custos Totais", formatar_real(custos))
            col3.metric("IRRF Retido", formatar_real(irrf))

            st.divider()
            
            if base_calculo > 0:
                imposto_devido = base_calculo * 0.20
                darf_pagar = imposto_devido - irrf
                
                # LÓGICA DE EXIBIÇÃO
                st.subheader("🧮 Fechamento")
                c_a, c_b = st.columns(2)
                c_a.text(f"  {formatar_real(lucro_liquido_op)} (Líquido Op.)")
                c_a.text(f"- {formatar_real(prej)} (Prejuízo Ant.)")
                c_a.text(f"= {formatar_real(base_calculo)} (Base Calc.)")
                
                c_b.text(f"  {formatar_real(imposto_devido)} (20% Imposto)")
                c_b.text(f"- {formatar_real(irrf)} (IRRF)")
                c_b.markdown(f"**= {formatar_real(darf_pagar)} (A PAGAR)**")
                
                if darf_pagar >= 10:
                    st.success(f"### ✅ GERAR DARF: {formatar_real(darf_pagar)}")
                elif darf_pagar > 0:
                    st.warning(f"### Acumular: {formatar_real(darf_pagar)}")
                    st.caption("Menor que R$ 10,00. Acumule para o mês que vem.")
                else:
                    st.success("### Isento (Saldo Credor)")
            
            else:
                st.error(f"### Prejuízo a Acumular: {formatar_real(abs(base_calculo))}")
                st.caption("Anote este valor para abater no próximo mês.")
