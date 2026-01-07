import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gym Trade Pro", layout="wide", page_icon="🏦")

# --- AUTENTICAÇÃO ---
try:
    chave = st.secrets["GOOGLE_API_KEY"]
except:
    chave = ""

if chave:
    genai.configure(api_key=chave)

# --- FUNÇÕES DE UTILIDADE ---

def formatar_real(valor):
    if not isinstance(valor, (int, float)): return "R$ 0,00"
    texto = f"R$ {valor:,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")

def converter_para_float(valor):
    if isinstance(valor, (int, float)): return float(valor)
    try:
        texto = str(valor).strip().upper()
        # Remove R$, espaços
        texto = texto.replace('R$', '').replace(' ', '')
        
        # Lógica de Sinal:
        # Se tiver 'D' (Débito) ou sinal negativo, é negativo.
        is_negative = 'D' in texto or '-' in texto
        
        # Limpa letras para converter
        texto = texto.replace('C', '').replace('D', '')
        
        # Padrão BR (1.000,00) -> US (1000.00)
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
    """Lista de modelos para tentar (Evita erro 404 e erro de Coach)"""
    return [
        "gemini-2.0-flash", 
        "gemini-2.5-flash", 
        "gemini-1.5-flash"
    ]

# --- FUNÇÃO DO COACH (CORRIGIDA) ---
def chamar_coach(resumo_texto):
    if not chave: return "Erro: Chave API não configurada."
    
    # Tenta modelos até um funcionar
    for nome in obter_modelo_seguro():
        try:
            model = genai.GenerativeModel(nome)
            # Prompt mais direto para evitar bloqueios
            response = model.generate_content(f"Aja como um mentor trader profissional. Análise curta: {resumo_texto}")
            return response.text
        except:
            continue
    return "O Coach está indisponível (Erro nos servidores do Google)."

# --- FUNÇÃO DO LEITOR DE NOTAS (LÓGICA HÍBRIDA) ---
def analisar_nota_cirurgica(arquivo_pdf):
    if not chave: return {"erro": "Chave API não configurada."}

    bytes_pdf = arquivo_pdf.getvalue()
    part_arquivo = {"mime_type": "application/pdf", "data": bytes_pdf}

    # PROMPT: PEÇA AS PEÇAS DO QUEBRA-CABEÇA, NÃO O RESULTADO FINAL.
    prompt = """
    Você é um Extrator de Dados Contábeis (OCR). Analise esta Nota de Corretagem.
    
    Extraia os seguintes valores BRUTOS (sem fazer contas):
    
    1. "soma_creditos_c": Olhe a tabela de negócios (Day Trade). Some TODOS os valores de Ajuste seguidos da letra 'C'.
    2. "soma_debitos_d": Olhe a tabela de negócios. Some TODOS os valores de Ajuste seguidos da letra 'D'.
    
    3. "rotulo_ajuste_daytrade": Procure se existe EXPLICITAMENTE um campo chamado "Ajuste Day Trade", "Total Líquido" ou "Total Nota".
       - Se existir, extraia o valor (Ex: 275,00 C).
       - Se NÃO existir ou for 0,00, retorne "0.00".
       
    4. "custos_totais": Some TODAS as taxas do rodapé (Taxa Operacional + Registro + Emolumentos + Corretagem + ISS).
    
    5. "irrf": Valor do "I.R.R.F." ou "IRRF Day Trade".
    
    Retorne JSON:
    {
        "soma_creditos_c": 0.00,
        "soma_debitos_d": 0.00,
        "rotulo_ajuste_daytrade": "0.00",
        "custos_totais": 0.00,
        "irrf": 0.00,
        "data_pregao": "DD/MM/AAAA",
        "corretora_detectada": "Nome da corretora (Clear/CM/Outra)"
    }
    """

    for nome_modelo in obter_modelo_seguro():
        try:
            model = genai.GenerativeModel(nome_modelo)
            response = model.generate_content([prompt, part_arquivo])
            dados = limpar_json(response.text)
            if "erro" not in dados:
                dados['modelo_usado'] = nome_modelo
                return dados
        except:
            continue
    
    return {"erro": "Não foi possível ler o PDF. Tente imprimir novamente."}


# --- INTERFACE ---
st.title("📈 Gym Trade Pro")

if not chave:
    st.error("⚠️ API Key ausente.")
    st.stop()

aba1, aba2 = st.tabs(["🏋️‍♂️ Treino (CSV)", "💰 Contador (PDF Universal)"])

# --- ABA 1: COACH ---
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
                
                if st.button("📢 Coach, analise meu dia"):
                    with st.spinner("Analisando..."):
                        msg = chamar_coach(f"Trader: {formatar_real(res)}, {trd} trades.")
                        st.info(f"🤖 **Coach:** {msg}")
                st.dataframe(df)

# --- ABA 2: LEITOR UNIVERSAL ---
with aba2:
    st.header("Leitor Fiscal Universal")
    
    c1,c2 = st.columns(2)
    pdf = c1.file_uploader("Nota PDF (Clear, CM, XP, etc)", type=["pdf"], key="pdf_uni")
    prej = c2.number_input("Prejuízo Anterior (R$)", 0.0, step=10.0)
    
    if pdf:
        with st.spinner("Extraindo dados e aplicando lógica contábil..."):
            dados = analisar_nota_cirurgica(pdf)
        
        if "erro" in dados:
            st.error(f"Erro: {dados['erro']}")
        else:
            # 1. Recupera valores brutos
            soma_c = converter_para_float(dados.get('soma_creditos_c', 0))
            soma_d = converter_para_float(dados.get('soma_debitos_d', 0)) # Já vem positivo do converter_abs
            ajuste_explicito = converter_para_float(dados.get('rotulo_ajuste_daytrade', 0))
            
            custos = converter_para_float(dados.get('custos_totais', 0))
            irrf = converter_para_float(dados.get('irrf', 0))
            data = dados.get('data_pregao', '-')
            corretora = dados.get('corretora_detectada', 'Genérica')
            
            # 2. LÓGICA DE DECISÃO PYTHON (O CÉREBRO)
            
            # Cenário CLEAR: O campo explícito existe e é relevante (maior que 1 real)
            # A Clear coloca "275,00 C" no campo Ajuste Day Trade.
            if abs(ajuste_explicito) > 1.0:
                bruto_final = ajuste_explicito
                metodo_calculo = "Campo 'Ajuste Day Trade' (Padrão Clear/XP)"
            
            # Cenário CM CAPITAL: O campo explícito é zero ou não existe.
            # Mas temos soma de Créditos e Débitos.
            else:
                # O converter_para_float já trata o sinal, mas aqui somamos as magnitudes
                # C é entrada (+), D é saída (-)
                # Nota: soma_d vem absoluta do json, então subtraímos.
                bruto_final = abs(soma_c) - abs(soma_d)
                metodo_calculo = "Cálculo Manual: Créditos (C) - Débitos (D) (Padrão CM/Genial)"
            
            # 3. CÁLCULO FINAL IMPOSTO
            # Lucro Líquido Operacional = Bruto - Custos
            # IMPORTANTE: Se o bruto for positivo, subtrai custos.
            # Se bruto for negativo (perda), custos aumentam o prejuízo.
            lucro_liquido_op = bruto_final - abs(custos)
            
            base_calculo = lucro_liquido_op - prej
            
            # --- VISUALIZAÇÃO ---
            st.success(f"Nota Processada: {data} | Corretora: {corretora}")
            
            with st.expander(f"📚 Detalhes da Auditoria ({metodo_calculo})"):
                st.write(f"Soma Créditos (C): {formatar_real(soma_c)}")
                st.write(f"Soma Débitos (D): {formatar_real(soma_d)}")
                st.write(f"Campo Explícito na Nota: {formatar_real(ajuste_explicito)}")
                st.write(f"Custos Identificados: {formatar_real(custos)}")
                st.markdown(f"**Bruto Definido:** {formatar_real(bruto_final)}")

            col1, col2, col3 = st.columns(3)
            cor_res = "normal" if bruto_final >= 0 else "inverse"
            col1.metric("Resultado Bruto", formatar_real(bruto_final), delta_color=cor_res)
            col2.metric("Custos Totais", formatar_real(custos))
            col3.metric("IRRF Retido", formatar_real(irrf))
            
            st.divider()
            
            if base_calculo > 0:
                imposto = base_calculo * 0.20
                pagar = imposto - irrf
                
                # Exibição da Memória de Cálculo
                st.subheader("🧮 Memória de Cálculo")
                st.code(f"""
                (+) Resultado Bruto:      {formatar_real(bruto_final)}
                (-) Custos Totais:        {formatar_real(custos)}
                (=) Líquido Operacional:  {formatar_real(lucro_liquido_op)}
                (-) Prejuízo Anterior:    {formatar_real(prej)}
                (=) Base de Cálculo:      {formatar_real(base_calculo)}
                (x) Alíquota 20%:         {formatar_real(imposto)}
                (-) IRRF já pago:         {formatar_real(irrf)}
                (=) A PAGAR:              {formatar_real(pagar)}
                """)
                
                if pagar >= 10:
                    st.success(f"### ✅ GERAR DARF: {formatar_real(pagar)}")
                elif pagar > 0:
                    st.warning(f"### Acumular: {formatar_real(pagar)}")
                    st.caption("Menor que R$ 10,00. Não pagar agora.")
                else:
                    st.success("### Isento (Saldo Credor)")
            else:
                st.error(f"### Prejuízo a Acumular: {formatar_real(abs(base_calculo))}")
