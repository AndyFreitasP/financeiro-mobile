import flet as ft
import time
import urllib.parse
import traceback # Para mostrar o erro na tela se houver

def main(page: ft.Page):
    # --- 1. Boot Seguro (Feedback Imediato) ---
    page.bgcolor = "#0f172a"
    page.title = "Andy Manager Safe"
    page.padding = 0
    
    # Texto de carregamento para você saber que o Python rodou
    loading_text = ft.Text("Carregando sistema...", color="white", size=12)
    page.add(ft.SafeArea(ft.Container(content=loading_text, padding=20)))

    try:
        # --- 2. DADOS (Banco em Memória) ---
        users_db = [
            {
                "id": 1, "nome": "Anderson (Pessoal)", 
                "transacoes": [
                    {"id": 101, "nome": "Salário", "valor": 4700.00, "tipo": "entrada", "data": "05/11"},
                    {"id": 102, "nome": "Internet", "valor": 100.00, "tipo": "saida", "data": "01/11"}
                ]
            },
            {
                "id": 2, "nome": "Casa / Família", 
                "transacoes": [
                    {"id": 201, "nome": "Aluguel", "valor": 1200.00, "tipo": "saida", "data": "10/11"}
                ]
            }
        ]

        # --- 3. FUNÇÕES LÓGICAS ---
        def formatar_moeda(valor):
            return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        def calcular_resumo(user_data):
            entradas = sum(t["valor"] for t in user_data["transacoes"] if t["tipo"] == "entrada")
            saidas = sum(t["valor"] for t in user_data["transacoes"] if t["tipo"] == "saida")
            return entradas, saidas, entradas - saidas

        # --- 4. TELAS (Design Simplificado - Sem Gradientes/Sombras) ---
        
        # TELA: DASHBOARD
        def show_dashboard(user_data):
            page.clean()
            
            # Elementos Reativos
            coluna_lancamentos = ft.Column(spacing=2)
            txt_saldo = ft.Text(size=28, weight="bold", color="white")
            
            def atualizar_tela():
                ent, sai, saldo = calcular_resumo(user_data)
                txt_saldo.value = f"R$ {formatar_moeda(saldo)}"
                txt_saldo.color = "#4ade80" if saldo >= 0 else "#f87171"
                
                coluna_lancamentos.controls.clear()
                if not user_data["transacoes"]:
                    coluna_lancamentos.controls.append(ft.Text("Sem lançamentos", color="grey"))
                else:
                    for item in reversed(user_data["transacoes"]):
                        cor = "#f87171" if item["tipo"] == "saida" else "#4ade80"
                        sinal = "-" if item["tipo"] == "saida" else "+"
                        
                        # Card Simples (Cor Sólida)
                        item_row = ft.Container(
                            padding=15, bgcolor="#1e293b", border_radius=5,
                            content=ft.Row([
                                ft.Column([ft.Text(item["nome"], color="white"), ft.Text(item["data"], size=10, color="grey")]),
                                ft.Row([
                                    ft.Text(f"{sinal} {formatar_moeda(item['valor'])}", color=cor, weight="bold"),
                                    ft.IconButton(ft.icons.DELETE, icon_color="grey", data=item["id"], on_click=deletar_item)
                                ])
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                        )
                        coluna_lancamentos.controls.append(item_row)
                page.update()

            def deletar_item(e):
                id_rem = e.control.data
                for item in user_data["transacoes"]:
                    if item["id"] == id_rem:
                        user_data["transacoes"].remove(item)
                        break
                atualizar_tela()
                page.show_snack_bar(ft.SnackBar(ft.Text("Item deletado")))

            # Modal Adicionar
            input_nome = ft.TextField(label="Nome", border_color="grey")
            input_val = ft.TextField(label="Valor", border_color="grey", keyboard_type=ft.KeyboardType.NUMBER)
            
            def add_ok(tipo):
                if input_nome.value and input_val.value:
                    try:
                        val = float(input_val.value.replace(",", "."))
                        user_data["transacoes"].append({"id": int(time.time()), "nome": input_nome.value, "valor": val, "tipo": tipo, "data": "Hoje"})
                        page.close(dlg_add)
                        atualizar_tela()
                    except: pass

            dlg_add = ft.AlertDialog(
                title=ft.Text("Novo"), content=ft.Column([input_nome, input_val], height=100),
                actions=[
                    ft.TextButton("Receita", on_click=lambda e: add_ok("entrada")),
                    ft.TextButton("Despesa", on_click=lambda e: add_ok("saida"))
                ], bgcolor="#1e293b"
            )

            # Montagem Dashboard
            atualizar_tela()
            
            page.add(ft.SafeArea(ft.Column([
                # Header
                ft.Row([
                    ft.IconButton(ft.icons.ARROW_BACK, icon_color="white", on_click=lambda e: show_users()),
                    ft.Text(user_data["nome"], size=18, weight="bold", color="white")
                ]),
                ft.Divider(color="grey"),
                
                # Card Saldo (Sem Gradiente)
                ft.Container(
                    content=ft.Column([
                        ft.Text("Saldo Atual", color="grey"),
                        txt_saldo
                    ]),
                    padding=20, bgcolor="#1e293b", border_radius=10, width=float("inf")
                ),
                
                ft.Container(height=20),
                
                # Botões Ação
                ft.Row([
                    ft.ElevatedButton("Novo Lançamento", bgcolor="#00d4ff", color="black", expand=True, on_click=lambda e: page.open(dlg_add)),
                ]),
                
                ft.Container(height=20),
                ft.Text("Histórico", color="white", weight="bold"),
                coluna_lancamentos
            ], scroll=ft.ScrollMode.AUTO, expand=True)))

        # TELA: LISTA DE USUÁRIOS
        def show_users():
            page.clean()
            lista = ft.Column(spacing=10)
            
            for user in users_db:
                card = ft.Container(
                    content=ft.Row([
                        ft.Text(user["nome"], size=16, color="white"),
                        ft.Icon(ft.icons.CHEVRON_RIGHT, color="grey")
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=20, bgcolor="#1e293b", border_radius=8,
                    on_click=lambda e, u=user: show_dashboard(u)
                )
                lista.controls.append(card)

            # Botão Criar Usuário
            input_new = ft.TextField(label="Nome", border_color="grey")
            def create_u(e):
                if input_new.value:
                    users_db.append({"id": len(users_db)+1, "nome": input_new.value, "transacoes": []})
                    page.close(dlg_new)
                    show_users()

            dlg_new = ft.AlertDialog(title=ft.Text("Novo Perfil"), content=input_new, actions=[ft.ElevatedButton("Salvar", on_click=create_u)], bgcolor="#1e293b")

            page.add(ft.SafeArea(ft.Column([
                ft.Row([
                    ft.Text("Perfis", size=24, weight="bold", color="white"),
                    ft.IconButton(ft.icons.EXIT_TO_APP, icon_color="red", on_click=lambda e: show_login())
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Container(height=20),
                lista,
                ft.Container(height=20),
                ft.ElevatedButton("Criar Perfil", bgcolor="#00d4ff", color="black", on_click=lambda e: page.open(dlg_new))
            ])))

        # TELA: LOGIN
        def show_login():
            page.clean()
            user_in = ft.TextField(label="Admin", border_color="grey", color="white")
            
            def login(e):
                if user_in.value:
                    show_users()
            
            page.add(ft.SafeArea(ft.Container(
                content=ft.Column([
                    ft.Icon(ft.icons.SECURITY, size=50, color="#00d4ff"),
                    ft.Text("ANDY MANAGER", size=20, weight="bold", color="white"),
                    ft.Container(height=20),
                    user_in,
                    ft.Container(height=10),
                    ft.ElevatedButton("ENTRAR", bgcolor="#00d4ff", color="black", width=200, on_click=login)
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                alignment=ft.alignment.center, expand=True
            )))

        # Inicia na tela de login
        show_login()

    except Exception as e:
        # SE DER ERRO, VAI APARECER NA TELA
        page.clean()
        page.add(ft.Text(f"ERRO CRÍTICO:\n{traceback.format_exc()}", color="red", size=14))

ft.app(target=main)
