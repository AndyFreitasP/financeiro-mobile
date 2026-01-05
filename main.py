import flet as ft
import sqlite3
from datetime import datetime
from fpdf import FPDF
import os

# ==============================================================================
# CONFIGURAÇÃO DE BANCO DE DADOS
# ==============================================================================
DB_NAME = "dados_financeiros.db"

# ==============================================================================
# FRONTEND E LÓGICA
# ==============================================================================
def main(page: ft.Page):
    page.title = "Andy Financeiro"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#000000"
    page.padding = 0
    
    # BANCO DE DADOS (Conexão Segura)
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS financeiro (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, descricao TEXT, categoria TEXT, tipo TEXT, valor REAL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS metas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor_alvo REAL, valor_atual REAL)")
        conn.commit()
    except Exception as e:
        page.add(ft.Text(f"Erro de Banco de Dados: {e}", color="red"))
        return

    # --- FUNÇÕES AUXILIARES ---
    def adicionar(data, desc, cat, tipo, valor):
        valor = abs(valor) * -1 if tipo == "Despesa" else abs(valor)
        cursor.execute("INSERT INTO financeiro (data, descricao, categoria, tipo, valor) VALUES (?, ?, ?, ?, ?)", (data, desc, cat, tipo, valor))
        conn.commit()

    def listar(mes_filtro=None):
        sql = "SELECT * FROM financeiro"
        params = []
        if mes_filtro:
            sql += " WHERE data LIKE ?"; params.append(f"%/{mes_filtro}")
        sql += " ORDER BY id DESC"
        cursor.execute(sql, params)
        return cursor.fetchall()

    def deletar(id_reg):
        cursor.execute("DELETE FROM financeiro WHERE id = ?", (id_reg,)); conn.commit()

    def get_meses():
        meses = set(); cursor.execute("SELECT data FROM financeiro")
        for row in cursor:
            try: meses.add((datetime.strptime(row[0], "%d/%m/%Y").year, datetime.strptime(row[0], "%d/%m/%Y").month))
            except: continue
        now = datetime.now(); meses.add((now.year, now.month))
        return [f"{m:02d}/{y}" for y, m in sorted(list(meses))]

    # --- UI ---
    menu_estado = {"atual": 0}
    conteudo_principal = ft.Container(expand=True, padding=10)

    # TELA EXTRATO
    def tela_extrato():
        lista_transacoes = ft.Column(spacing=10, scroll="auto", expand=True)
        txt_saldo = ft.Text("R$ 0,00", size=30, weight="bold")
        
        def atualizar_extrato(e=None):
            mes = dropdown_mes.value
            dados = listar(mes_filtro=mes)
            lista_transacoes.controls.clear()
            saldo_total = sum(row[5] for row in dados)
            if not dados:
                lista_transacoes.controls.append(ft.Container(content=ft.Text("Sem registros.", color="grey"), alignment=ft.alignment.center, padding=20))
            for row in dados:
                id_db, data, desc, cat, tipo, valor = row
                cor = "#FF5555" if valor < 0 else "#00FF7F"
                lista_transacoes.controls.append(
                    ft.Container(content=ft.Row([
                            ft.Column([ft.Text(data[:5], weight="bold"), ft.Text(cat, size=10, color="grey")]),
                            ft.Container(content=ft.Text(desc, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), expand=True, padding=ft.padding.only(left=10)),
                            ft.Column([ft.Text(f"R$ {valor:.2f}", color=cor, weight="bold"), ft.Container(content=ft.Icon(ft.Icons.DELETE_OUTLINE, color="#444444", size=18), on_click=lambda e, x=id_db: (deletar(x), atualizar_extrato()))], alignment="center", horizontal_alignment="end")
                        ]), bgcolor="#111111", padding=15, border_radius=10, border=ft.border.only(left=ft.BorderSide(4, cor)))
                )
            txt_saldo.value = f"R$ {saldo_total:,.2f}"
            txt_saldo.color = "#FF5555" if saldo_total < 0 else "#00FF7F"
            try: page.update()
            except: pass

        def adicionar_btn(e):
            try: val = float(txt_valor.value.replace(",", "."))
            except: return
            adicionar(txt_data.value, txt_desc.value, txt_cat.value, dd_tipo.value, val)
            txt_desc.value = ""; txt_valor.value = ""
            atualizar_extrato()

        meses = get_meses(); mes_atual = f"{datetime.now().month:02d}/{datetime.now().year}"
        if mes_atual not in meses: meses.append(mes_atual)
        
        dropdown_mes = ft.Dropdown(options=[ft.dropdown.Option(m) for m in meses], value=mes_atual, width=120, bgcolor="#111", border_radius=10, on_change=atualizar_extrato)
        txt_data = ft.TextField(label="Data", value=datetime.now().strftime("%d/%m/%Y"), bgcolor="#111", border_radius=8, expand=1)
        dd_tipo = ft.Dropdown(options=[ft.dropdown.Option("Despesa"), ft.dropdown.Option("Receita")], value="Despesa", bgcolor="#111", border_radius=8, expand=1)
        txt_desc = ft.TextField(label="Descrição", bgcolor="#111", border_radius=8, expand=2)
        txt_valor = ft.TextField(label="Valor", keyboard_type="number", bgcolor="#111", border_radius=8, expand=1)
        txt_cat = ft.TextField(label="Categoria", bgcolor="#111", border_radius=8)
        
        layout = ft.Column([
            ft.Row([ft.Text("HISTÓRICO", weight="bold", color="grey"), dropdown_mes], alignment="spaceBetween"),
            ft.Container(content=txt_saldo, alignment=ft.alignment.center, padding=15, border_radius=15, bgcolor="#111", border=ft.border.all(1, "#222")),
            lista_transacoes,
            ft.ExpansionTile(title=ft.Text("Novo Lançamento", size=14, color="grey"), controls=[
                ft.Container(content=ft.Column([ft.Row([txt_data, dd_tipo]), ft.Row([txt_desc, txt_valor]), txt_cat, ft.ElevatedButton("Lançar", on_click=adicionar_btn, bgcolor="#007ACC", color="white")]), padding=10, bgcolor="#0A0A0A")
            ])
        ], expand=True)
        atualizar_extrato()
        return layout

    # MENU E NAVEGAÇÃO
    def mudar_tela(idx):
        conteudo_principal.content = tela_extrato() if idx == 0 else ft.Text("Em desenvolvimento", text_align="center")
        page.update()

    barra_inferior = ft.NavigationBar(
        destinations=[
            ft.NavigationDestination(icon=ft.Icons.LIST_ALT, label="Extrato"),
            ft.NavigationDestination(icon=ft.Icons.SAVINGS_OUTLINED, label="Cofrinho"),
        ],
        on_change=lambda e: mudar_tela(e.control.selected_index),
        bgcolor="#111111",
    )

    # --- FUNDO E MONTAGEM ---
    # Tenta usar o ícone local se existir, senão usa URL para não travar (TELA PRETA FIX)
    imagem_src = "icon.png" # O Flet busca na assets_dir automaticamente
    
    imagem_fundo = ft.Image(src=imagem_src, fit=ft.ImageFit.CONTAIN, opacity=0.05)

    page.add(
        ft.Stack([
            ft.Container(imagem_fundo, alignment=ft.alignment.center),
            ft.Column([conteudo_principal, ft.Container(content=ft.Text("Powered by AndyP", size=10, color="#333", italic=True), alignment=ft.alignment.center), barra_inferior], expand=True)
        ], expand=True)
    )

# IMPORTANTE: assets_dir="assets" diz ao Flet onde buscar o icon.png
if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
