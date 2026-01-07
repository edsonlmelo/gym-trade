import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import re

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gym Trade Pro", layout="wide", page_icon="🚀")

try:
    chave = st.secrets["GOOGLE_API_KEY"]
except:
    chave = ""

if chave:
    genai.configure(api_key=chave)

# --- FUNÇÕES ÚTEIS ---
def formatar_real(valor):
    if not isinstance(valor, (int, float)): return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def converter_para_float(valor):
    if isinstance(valor, (int, float)): return float(valor)
    try:
        texto = str(valor).strip().upper()
        # Remove caracteres não numéricos mas mantém sinal negativo se houver
        is_negative = 'D' in texto or '-' in texto
        texto = texto.replace('R$', '').replace(' ', '').replace('C', '').replace('D', '')
        if ',' in texto: texto = texto.replace('.', '').replace(',', '.')
        num = float(texto)
        return -abs(num) if is_negative else abs(num)
    except: return 0.0

def limpar_json(texto):
    try:
        match = re.search(r'\{.*\}', texto, re.DOTALL)
        if match: return json.loads(match.group(0))
        return {"erro": "Erro no JSON"}
    except: return {"erro": "Erro JSON"}

def obter_modelos_seguros():
    return ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

# --- FUNÇÃO COACH BLINDADA ---
def chamar_coach(texto_usuario):
    if not chave: return "Erro: Configure a API Key."
    
    for modelo in obter_modelos_seguros():
        try:
            ia = genai.GenerativeModel(modelo)
            resp = ia.generate_content(f"Aja como um Coach Trader experiente e direto. Analise: {texto_usuario}")
            return resp.text
        except: continue
    return "Coach indisponível no momento."

# --- LEITOR INTELIGENTE V9 ---
def ler_nota_corretagem(arquivo_pdf):
    if not chave: return {"erro": "Sem API Key."}

    bytes_pdf = arquivo_pdf.getvalue()
    part = {"mime_type": "application/pdf", "data": bytes_pdf}

    # PROMPT CORRIGIDO COM SUA OBSERVAÇÃO
    prompt = """
    Você é um extrator de dados financeiros de Notas de Corretagem (Brasil).
    
    OBJETIVO: Extrair valores exatos para apuração de Imposto de Renda.
    
    CAMPO 1: "valor_bruto_negocios"
    - Procure no CORPO ou RESUMO da nota pelos campos: "Valor dos Negócios", "Ajuste Day Trade" ou "Total Líquido".
    - Na CM Capital, este valor pode estar no meio da página (Ex: 30,00 C).
    - Na Clear, geralmente está no topo (Ajuste Day Trade).
    - Se tiver letra 'C', é positivo. Se 'D', é negativo.
    
    CAMPO 2: "custos_totais"
    - Procure no RODAPÉ ou RESUMO FINANCEIRO.
    - Some: "Total de despesas" OU (Taxa Operacional + Registro + Emolumentos + Corretagem + ISS).
    
    CAMPO 3: "irrf"
    - Valor do "I.R.R.F. s/ operações" ou "IRRF Day Trade".
    
    CAMPO 4 (Fallback): "soma_creditos" e "soma_debitos"
    - Caso não encontre o Valor dos Negócios, some os ajustes C e D da tabela de operações.
    
    Retorne JSON:
    {
        "valor_bruto_negocios": "0.00",
        "custos_totais": "0.00",
        "irrf": "0.00",
        "soma_creditos": "0.00",
        "soma_debitos": "0.00",
        "data_pregao": "DD/MM/AAAA",
        "corretora_detectada": "Nome"
    }
    """
    
    for modelo in obter_modelos_seguros():
        try:
            ia = genai.GenerativeModel(modelo)
            resp = ia.generate_content([prompt, part])
            dados = limpar_json(resp.text)
            if "erro" not in dados:
                return dados
        except: continue
        
    return {"erro": "Falha na leitura do PDF."}

# --- INTERFACE ---
st.title("🎯 Gym Trade Pro")

aba_treino, aba_contador = st.tabs(["📊 Relatório Profit", "📝 Leitor Fiscal (Universal)"])

# ABA 1: PROFIT + COACH
with aba_treino:
    up = st.file_uploader("Relatório CSV", type=["csv"])
    if up:
        try:
            s = up.getvalue().decode('latin1').split('\n')
            i = next((x for x, l in enumerate(s) if "Ativo" in l and ";" in l), 0)
            df = pd.read_csv(io.StringIO('\n'.join(s[i:])), sep=';', encoding='latin1')
            
            col = next((c for c in df.columns if ('Res' in c or 'Lucro' in c) and ('Op' in c or 'Liq' in c)), None)
            
            if col:
                df['V'] = df[col].apply(converter_para_float)
                total = df['V'].sum()
                trades = len(df)
                
                c1, c2 = st.columns(2)
                c1.metric("Resultado Dia", formatar_real(total))
                c2.metric("Trades", trades)
                
                if st.button("🧠 Coach, analise"):
                    with st.spinner("Analisando..."):
                        msg = chamar_coach(f"Fiz {formatar_real(total)} em {trades} operações.")
                        st.info(f"💡 {msg}")
                        
                st.dataframe(df)
        except Exception as e:
            st.error(f"Erro CSV: {e}")

# ABA 2: NOTA DE CORRETAGEM
with aba_contador:
    st.info("Funciona com: Clear, CM Capital, XP, BTG, Genial (Lê 'Valor dos Negócios' ou 'Ajuste').")
    
    c1, c2 = st.columns(2)
    pdf = c1.file_uploader("Upload da Nota (PDF)", type=["pdf"])
    prejuizo = c2.number_input("Prejuízo Anterior", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Auditando Nota..."):
            d = ler_nota_corretagem(pdf)
        
        if "erro" in d:
            st.error(d["erro"])
        else:
            # DADOS
            vlr_negocios = converter_para_float(d.get('valor_bruto_negocios', 0))
            creditos = converter_para_float(d.get('soma_creditos', 0))
            debitos = converter_para_float(d.get('soma_debitos', 0))
            
            custos = converter_para_float(d.get('custos_totais', 0))
            irrf = converter_para_float(d.get('irrf', 0))
            data = d.get('data_pregao', '-')
            corretora = d.get('corretora_detectada', 'Detectada')
            
            # LÓGICA DE PRIORIDADE:
            # 1. Tenta usar o "Valor dos Negócios" que a nota traz (Ex: 30,00 na CM, 275,00 na Clear).
            # 2. Se a IA não achou (0,00), usa o cálculo C - D.
            if abs(vlr_negocios) > 0.01:
                bruto = vlr_negocios
                fonte = "Campo 'Valor dos Negócios/Ajuste' (Lido da Nota)"
            else:
                bruto = abs(creditos) - abs(debitos)
                fonte = "Cálculo Manual (Soma Créditos - Soma Débitos)"
            
            # CÁLCULOS FINAIS
            # Líquido Operacional = Bruto (Ajuste) - Custos
            # Se bruto for positivo (lucro), desconta custos.
            # Se bruto for negativo (prejuízo), soma custos (aumenta o prejuízo).
            liquido_op = bruto - abs(custos)
            base = liquido_op - prejuizo
            
            st.success(f"Nota Processada: {data} | {corretora}")
            
            with st.expander(f"🔍 Detalhes da Leitura ({fonte})"):
                st.write(f"Valor Lido na Nota: {formatar_real(vlr_negocios)}")
                st.write(f"Cálculo C-D (Prova Real): {formatar_real(abs(creditos) - abs(debitos))}")
                st.write(f"Custos Totais: {formatar_real(custos)}")
            
            k1, k2, k3 = st.columns(3)
            cor = "normal" if bruto >= 0 else "inverse"
            k1.metric("Bruto (Ajuste)", formatar_real(bruto), delta_color=cor)
            k2.metric("Custos", formatar_real(custos))
            k3.metric("Líquido Op.", formatar_real(liquido_op))
            
            st.divider()
            
            if base > 0:
                imposto = base * 0.20
                darf = imposto - irrf
                
                st.subheader("🧾 Darf a Pagar")
                st.code(f"""
                (+) Bruto:       {formatar_real(bruto)}
                (-) Custos:      {formatar_real(custos)}
                (=) Líquido Op:  {formatar_real(liquido_op)}
                (-) Prej. Ant:   {formatar_real(prej)}
                (=) Base Calc:   {formatar_real(base)}
                (x) 20%:         {formatar_real(imposto)}
                (-) IRRF Pago:   {formatar_real(irrf)}
                (=) A PAGAR:     {formatar_real(darf)}
                """)
                
                if darf >= 10:
                    st.success(f"### ✅ PAGAR: {formatar_real(darf)}")
                elif darf > 0:
                    st.warning(f"### Acumular: {formatar_real(darf)}")
                else:
                    st.success("### Isento")
            else:
                st.error(f"### Prejuízo a Acumular: {formatar_real(abs(base))}")
