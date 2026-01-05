import flet as ft
import sqlite3
from datetime import datetime
from fpdf import FPDF
import os

# ==============================================================================
# 0. FUNÇÕES UTILITÁRIAS (SEGURANÇA)
# ==============================================================================
def borda_segura(width, color):
    try: return ft.Border.all(width, color)
    except: return ft.border.all(width, color)

def padding_only(left=0, top=0, right=0, bottom=0):
    try: return ft.Padding.only(left, top, right, bottom)
    except: return ft.padding.only(left, top, right, bottom)

def border_only_left(width, color):
    side = ft.BorderSide(width, color)
    try: return ft.Border.only(left=side)
    except: return ft.border.only(left=side)

# ==============================================================================
# 1. ENGINE DE RELATÓRIOS (PDF)
# ==============================================================================
class RelatorioPDF(FPDF):
    def __init__(self, cor_tema):
        super().__init__()
        self.cor_r, self.cor_g, self.cor_b = cor_tema

    def header(self):
        self.set_fill_color(self.cor_r, self.cor_g, self.cor_b)
        self.rect(0, 0, 210, 35, 'F')
        self.set_y(10)
        self.set_font('Arial', 'B', 18)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, 'RELATÓRIO FINANCEIRO', 0, 1, 'C')
        self.set_font('Arial', '', 9)
        self.cell(0, 5, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1, 'C')
        self.ln(20)

def gerar_pdf_financeiro(dados, saldo_total, mes_referencia):
    cor_tema = (46, 204, 113) if saldo_total >= 0 else (231, 76, 60)
    texto_situacao = "POSITIVO" if saldo_total >= 0 else "NEGATIVO"
    pdf = RelatorioPDF(cor_tema)
    pdf.add_page()
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, txt=f"Referência: {mes_referencia}", ln=True)
    pdf.set_font("Arial", "B", 14)
    pdf.write(8, "Saldo Final: ")
    pdf.set_text_color(*cor_tema)
    pdf.write(8, f"R$ {saldo_total:,.2f} ({texto_situacao})")
    pdf.ln(15)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(30, 10, "Data", 1, 0, 'C', 1)
    pdf.cell(100, 10, "Descrição", 1, 0, 'L', 1)
    pdf.cell(40, 10, "Valor", 1, 1, 'R', 1)
    pdf.set_font("Arial", "", 10)
    for row in dados:
        data, desc, valor = row[1], row[2], row[5]
        pdf.set_text_color(0, 0, 0)
        pdf.cell(30, 8, data, 1, 0, 'C')
        pdf.set_text_color(50, 50, 50)
        pdf.cell(100, 8, f" {desc[:45]}", 1, 0, 'L')
        pdf.set_text_color(231, 76, 60) if valor < 0 else pdf.set_text_color(46, 204, 113)
        pdf.cell(40, 8, f"R$ {valor:.2f} ", 1, 1, 'R')
    nome_arquivo = f"extrato_{mes_referencia.replace('/', '_')}.pdf"
    pdf.output(nome_arquivo)
    return nome_arquivo

# ==============================================================================
# 2. BACKEND
# ==============================================================================
class BancoDeDados:
    def __init__(self):
        self.conn = sqlite3.connect("dados_financeiros.db", check_same_thread=False)
        self.inicializar()
    def inicializar(self):
        cursor = self.conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS financeiro (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, descricao TEXT, categoria TEXT, tipo TEXT, valor REAL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS metas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor_alvo REAL, valor_atual REAL)")
        self.conn.commit()
    def adicionar(self, data, desc, cat, tipo, valor):
        valor = abs(valor) * -1 if tipo == "Despesa" else abs(valor)
        self.conn.cursor().execute("INSERT INTO financeiro (data, descricao, categoria, tipo, valor) VALUES (?, ?, ?, ?, ?)", (data, desc, cat, tipo, valor))
        self.conn.commit()
    def listar(self, mes_filtro=None):
        sql = "SELECT * FROM financeiro"
        params = []
        if mes_filtro:
            sql += " WHERE data LIKE ?"; params.append(f"%/{mes_filtro}")
        sql += " ORDER BY id DESC"
        cursor = self.conn.cursor(); cursor.execute(sql, params)
        return cursor.fetchall()
    def deletar(self, id_reg):
        self.conn.cursor().execute("DELETE FROM financeiro WHERE id = ?", (id_reg,)); self.conn.commit()
    def get_meses(self):
        meses = set(); cursor = self.conn.cursor(); cursor.execute("SELECT data FROM financeiro")
        for row in cursor:
            try: meses.add((datetime.strptime(row[0], "%d/%m/%Y").year, datetime.strptime(row[0], "%d/%m/%Y").month))
            except: continue
        now = datetime.now(); meses.add((now.year, now.month))
        return [f"{m:02d}/{y}" for y, m in sorted(list(meses))]
    def criar_meta(self, nome, alvo):
        self.conn.cursor().execute("INSERT INTO metas (nome, valor_alvo, valor_atual) VALUES (?, ?, 0)", (nome, alvo)); self.conn.commit()
    def atualizar_meta(self, idm, val):
        self.conn.cursor().execute("UPDATE metas SET valor_atual = valor_atual + ? WHERE id = ?", (val, idm)); self.conn.commit()
    def listar_metas(self):
        cursor = self.conn.cursor(); cursor.execute("SELECT * FROM metas"); return cursor.fetchall()
    def deletar_meta(self, idm):
        self.conn.cursor().execute("DELETE FROM metas WHERE id = ?", (idm,)); self.conn.commit()

# ==============================================================================
# 3. FRONTEND (V40 - STRINGS PURAS)
# ==============================================================================
def main(page: ft.Page):
    page.title = "Financeiro V40"
    # FIX: Usando string "dark" em vez de Enum para evitar erro
    page.theme_mode = "dark" 
    page.bgcolor = "#000000"
    page.padding = 0
    page.scroll = None 

    db = BancoDeDados()
    menu_estado = {"atual": 0}
    
    # Container transparente para ver o fundo
    conteudo_principal = ft.Container(expand=True, padding=10, bgcolor=None)

    # --- TELAS ---
    def tela_extrato():
        lista_transacoes = ft.Column(spacing=10, scroll="auto", expand=True)
        txt_saldo = ft.Text("R$ 0,00", size=30, weight="bold")
        def atualizar_extrato(e=None):
            mes = dropdown_mes.value
            dados = db.listar(mes_filtro=mes)
            lista_transacoes.controls.clear()
            saldo_total = sum(row[5] for row in dados)
            if not dados:
                lista_transacoes.controls.append(ft.Container(content=ft.Text("Nenhum lançamento neste mês.", color="grey"), padding=20, alignment=ft.Alignment(0, 0)))
            for row in dados:
                id_db, data, desc, cat, tipo, valor = row
                cor = "#FF5555" if valor < 0 else "#00FF7F"
                lista_transacoes.controls.append(
                    ft.Container(content=ft.Row([
                            ft.Column([ft.Text(data[:5], weight="bold"), ft.Text(cat, size=10, color="grey")]),
                            ft.Container(content=ft.Text(desc, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), expand=True, padding=padding_only(left=10)),
                            # FIX: Strings puras para alinhamento
                            ft.Column([ft.Text(f"R$ {valor:.2f}", color=cor, weight="bold"), ft.Container(content=ft.Text("X", color="#555555"), on_click=lambda e, x=id_db: deletar_extrato(x))], alignment="center", horizontal_alignment="end")
                        ]), bgcolor="#1A1A1A", padding=15, border_radius=10, border=border_only_left(4, cor))
                )
            txt_saldo.value = f"R$ {saldo_total:,.2f}"
            txt_saldo.color = "#FF5555" if saldo_total < 0 else "#00FF7F"
            try: txt_saldo.update(); lista_transacoes.update()
            except: pass
        def adicionar_extrato(e):
            try: val = float(txt_valor.value.replace(",", "."))
            except: return
            db.adicionar(txt_data.value, txt_desc.value, txt_cat.value, dd_tipo.value, val)
            txt_desc.value = ""; txt_cat.value = ""; txt_valor.value = ""
            atualizar_extrato()
        def deletar_extrato(x): db.deletar(x); atualizar_extrato()
        def acao_pdf(e):
            mes = dropdown_mes.value; dados = db.listar(mes); saldo = sum(r[5] for r in dados)
            try: os.startfile(gerar_pdf_financeiro(dados, saldo, mes))
            except: pass
        meses = db.get_meses(); mes_atual = f"{datetime.now().month:02d}/{datetime.now().year}"
        if mes_atual not in meses: meses.append(mes_atual)
        
        dropdown_mes = ft.Dropdown(options=[ft.dropdown.Option(m) for m in meses], value=mes_atual, width=140, bgcolor="#1f1f1f", border_radius=10); dropdown_mes.on_change = atualizar_extrato
        txt_data = ft.TextField(label="Data", value=datetime.now().strftime("%d/%m/%Y"), bgcolor="#1f1f1f", border_radius=8, expand=1)
        dd_tipo = ft.Dropdown(options=[ft.dropdown.Option("Despesa"), ft.dropdown.Option("Receita")], value="Despesa", bgcolor="#1f1f1f", border_radius=8, expand=1)
        
        # Hints
        txt_desc = ft.TextField(label="Descrição", hint_text="Ex: Netflix...", bgcolor="#1f1f1f", border_radius=8, expand=2)
        txt_valor = ft.TextField(label="Valor", hint_text="0,00", keyboard_type="number", bgcolor="#1f1f1f", border_radius=8, expand=1)
        txt_cat = ft.TextField(label="Categoria", hint_text="Ex: Lazer...", bgcolor="#1f1f1f", border_radius=8)
        
        # FIX: Alignment manual (0,0)
        btn_lancar = ft.Container(content=ft.Text("LANÇAR", weight="bold"), bgcolor="#007ACC", padding=15, alignment=ft.Alignment(0, 0), border_radius=8, on_click=adicionar_extrato)
        btn_pdf = ft.Container(content=ft.Text("PDF", weight="bold"), bgcolor="#2E8B57", padding=15, alignment=ft.Alignment(0, 0), border_radius=8, on_click=acao_pdf)
        
        layout = ft.Column([
            ft.Row([ft.Text("Mês:", color="grey"), dropdown_mes], alignment="center"),
            ft.Container(content=txt_saldo, alignment=ft.Alignment(0, 0), padding=20, border_radius=15, bgcolor="#1f1f1f", border=borda_segura(1, "#333")),
            ft.Text("Extrato", weight="bold", color="grey"), lista_transacoes, ft.Divider(color="transparent"), btn_pdf, ft.Divider(),
            ft.Text("Novo Lançamento", weight="bold"), ft.Container(content=ft.Column([ft.Row([txt_data, dd_tipo]), ft.Row([txt_desc, txt_valor]), txt_cat, ft.Container(height=5), btn_lancar]), padding=15, bgcolor="#1A1A1A", border_radius=10)
        ], expand=True, spacing=15)
        atualizar_extrato()
        return ft.Container(content=layout, expand=True)

    def tela_cofrinho():
        lista_metas = ft.Column(spacing=15, scroll="auto", expand=True)
        def atualizar_metas(e=None):
            lista_metas.controls.clear()
            for m in db.listar_metas():
                idm, nome, alvo, atual = m
                prog = atual / alvo if alvo > 0 else 0
                if prog > 1: prog = 1
                cor_barra = "#00FF7F" if prog >= 1 else "#007ACC"
                lista_metas.controls.append(ft.Container(content=ft.Column([
                    ft.Row([ft.Text(nome, weight="bold", size=16), ft.Container(content=ft.Text("X", color="red"), on_click=lambda e, x=idm: (db.deletar_meta(x), atualizar_metas()))], alignment="spaceBetween"),
                    ft.ProgressBar(value=prog, color=cor_barra, bgcolor="#333333", height=10),
                    ft.Row([ft.Text(f"R$ {atual:,.0f}", color="grey"), ft.Text(f"Meta: R$ {alvo:,.0f}", color="grey"), ft.Text(f"{int(prog*100)}%", color=cor_barra)], alignment="spaceBetween"),
                    ft.Row([ft.TextField(label="+", hint_text="R$", width=80, height=40, text_size=12, bgcolor="#222", border_radius=5, on_submit=lambda e, idx=idm: (db.atualizar_meta(idx, float(e.control.value.replace(",","."))), atualizar_metas())), ft.Container(content=ft.Text("Depositar", size=12), padding=10, bgcolor="#333", border_radius=5, on_click=lambda e, idx=idm: (db.atualizar_meta(idx, float(e.control.data.value.replace(",","."))), atualizar_metas()))], alignment="end")
                ]), bgcolor="#1A1A1A", padding=15, border_radius=10, border=borda_segura(1, "#333")))
                lista_metas.controls[-1].content.controls[3].controls[1].data = lista_metas.controls[-1].content.controls[3].controls[0]
            try: lista_metas.update()
            except: pass
        
        txt_nome = ft.TextField(label="Meta", hint_text="Ex: Viagem...", bgcolor="#1f1f1f", border_radius=8)
        txt_alvo = ft.TextField(label="Alvo", hint_text="Total", keyboard_type="number", bgcolor="#1f1f1f", border_radius=8)
        btn_criar = ft.Container(content=ft.Text("CRIAR", weight="bold"), bgcolor="#007ACC", padding=15, alignment=ft.Alignment(0, 0), border_radius=8, on_click=lambda e: (db.criar_meta(txt_nome.value, float(txt_alvo.value.replace(",","."))), atualizar_metas()))
        layout = ft.Column([ft.Text("Cofrinhos", size=20, weight="bold"), lista_metas, ft.Divider(), ft.Text("Nova Meta", size=16), txt_nome, txt_alvo, btn_criar], expand=True, spacing=15)
        atualizar_metas()
        return ft.Container(content=layout, expand=True)

    def tela_simulador():
        def calcular(e):
            try:
                receita = float(txt_receita.value.replace(",", ".") or 0)
                gastos = sum(float(x.value.replace(",", ".") or 0) for x in [txt_g1, txt_g2, txt_g3])
                sobra = receita - gastos
                lbl_res.value = f"Sobra: R$ {sobra:,.2f}"
                lbl_res.color = "#00FF7F" if sobra >= 0 else "#FF5555"
                page.update()
            except: pass
        
        txt_receita = ft.TextField(label="Renda", hint_text="Salário", bgcolor="#1f1f1f", border_radius=8); txt_receita.on_change = calcular
        txt_g1 = ft.TextField(label="Gasto 1", hint_text="Fixo", bgcolor="#1f1f1f", border_radius=8); txt_g1.on_change = calcular
        txt_g2 = ft.TextField(label="Gasto 2", hint_text="Variável", bgcolor="#1f1f1f", border_radius=8); txt_g2.on_change = calcular
        txt_g3 = ft.TextField(label="Gasto 3", hint_text="Outros", bgcolor="#1f1f1f", border_radius=8); txt_g3.on_change = calcular
        lbl_res = ft.Text("Sobra: R$ 0,00", size=20, weight="bold")
        layout = ft.Column([ft.Text("Simulador", size=20, weight="bold"), ft.Divider(), txt_receita, ft.Text("Despesas"), txt_g1, txt_g2, txt_g3, ft.Divider(), ft.Container(content=lbl_res, bgcolor="#1A1A1A", padding=20, border_radius=10, alignment=ft.Alignment(0, 0))], scroll="auto", spacing=15)
        return ft.Container(content=layout, expand=True)

    def mudar_tela(index):
        menu_estado["atual"] = index
        conteudo_principal.content = [tela_extrato(), tela_cofrinho(), tela_simulador()][index]
        redesenhar_botoes()
        page.update()

    def redesenhar_botoes():
        idx = menu_estado["atual"]
        c0 = "#007ACC" if idx == 0 else "grey"
        c1 = "#007ACC" if idx == 1 else "grey"
        c2 = "#007ACC" if idx == 2 else "grey"
        barra_inferior.content = ft.Row([
            ft.Container(content=ft.Column([ft.Text("☰", color=c0, size=24), ft.Text("Extrato", color=c0, size=10)], alignment="center", horizontal_alignment="center", spacing=2), on_click=lambda e: mudar_tela(0), expand=True, padding=5),
            ft.Container(content=ft.Column([ft.Text("$", color=c1, size=24, weight="bold"), ft.Text("Cofrinho", color=c1, size=10)], alignment="center", horizontal_alignment="center", spacing=2), on_click=lambda e: mudar_tela(1), expand=True, padding=5),
            ft.Container(content=ft.Column([ft.Text("∑", color=c2, size=24, weight="bold"), ft.Text("Simular", color=c2, size=10)], alignment="center", horizontal_alignment="center", spacing=2), on_click=lambda e: mudar_tela(2), expand=True, padding=5),
        ], alignment="spaceEvenly")

    barra_inferior = ft.Container(height=70, bgcolor="#111111", border=ft.border.only(top=ft.BorderSide(1, "#333333")), alignment=ft.Alignment(0, 0))

    redesenhar_botoes() 
    conteudo_principal.content = tela_extrato() 

    # === IMAGEM DE FUNDO (FIX: STRING PURA "COVER") ===
    imagem_fundo = ft.Image(
        src="https://img.freepik.com/free-photo/abstract-luxury-gradient-blue-background-smooth-dark-blue-with-black-vignette_1258-48251.jpg",
        fit="cover", # <--- AQUI ESTAVA O ERRO, AGORA É STRING
        opacity=0.1 
    )

    page.add(
        ft.Stack([
            imagem_fundo, 
            ft.Column([   
                conteudo_principal, 
                barra_inferior      
            ], expand=True, spacing=0)
        ], expand=True)
    )

if __name__ == "__main__":
    ft.app(target=main)
