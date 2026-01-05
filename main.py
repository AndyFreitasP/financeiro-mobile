import flet as ft
import time
import urllib.parse

def main(page: ft.Page):
    # --- 1. Configurações Visuais (Tema Dark/Gótico Tech) ---
    page.title = "Andy Financeiro Manager"
    page.padding = 0
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0f172a" # Fundo Azul Profundo (Slate 900)

    # --- 2. BANCO DE DADOS (Em Memória) ---
    # Estrutura inicial para testes. 
    # Dica: No futuro, isso pode vir de um arquivo SQLite.
    users_db = [
        {
            "id": 1, 
            "nome": "Anderson (Pessoal)", 
            "transacoes": [
                {"id": 101, "nome": "Salário", "valor": 4700.00, "tipo": "entrada", "data": "05/11"},
                {"id": 102, "nome": "Internet Fibra", "valor": 100.00, "tipo": "saida", "data": "01/11"},
                {"id": 103, "nome": "Spotify", "valor": 21.90, "tipo": "saida", "data": "02/11"}
            ]
        },
        {
            "id": 2, 
            "nome": "Casa / Família", 
            "transacoes": [
                {"id": 201, "nome": "Aluguel", "valor": 1200.00, "tipo": "saida", "data": "10/11"},
                {"id": 202, "nome": "Conta de Luz", "valor": 150.00, "tipo": "saida", "data": "Agendado"}
            ]
        }
    ]

    # --- 3. Funções Auxiliares ---
    
    # Deep Link para o Google Agenda
    def abrir_google_agenda(nome_conta, valor_conta):
        try:
            titulo = urllib.parse.quote(f"Pagar: {nome_conta}")
            detalhes = urllib.parse.quote(f"Valor: R$ {valor_conta}\nLembrete via Andy Financeiro.")
            url = f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={titulo}&details={detalhes}"
            page.launch_url(url)
            page.show_snack_bar(ft.SnackBar(ft.Text("Abrindo agenda... Confirme a data lá!")))
        except:
            page.show_snack_bar(ft.SnackBar(ft.Text("Erro ao abrir agenda.")))

    # Formata moeda (Ex: 1200.0 -> 1.200,00)
    def formatar_moeda(valor):
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # Calcula totais dinamicamente com base nas transações atuais
    def calcular_resumo(user_data):
        entradas = sum(t["valor"] for t in user_data["transacoes"] if t["tipo"] == "entrada")
        saidas = sum(t["valor"] for t in user_data["transacoes"] if t["tipo"] == "saida")
        saldo = entradas - saidas
        return entradas, saidas, saldo

    # --- 4. TELA: Dashboard (Gerenciamento) ---
    def show_dashboard(user_data):
        page.clean()
        
        # Variáveis reativas para atualizar a tela sem recarregar tudo
        txt_saldo = ft.Text(size=30, weight="bold", color="white")
        txt_entradas = ft.Text(size=14, weight="bold", color="white")
        txt_saidas = ft.Text(size=14, weight="bold", color="white")
        coluna_lancamentos = ft.Column(spacing=10)

        # Função Core: Atualiza os dados na tela
        def atualizar_dados():
            entradas, saidas, saldo = calcular_resumo(user_data)
            
            # Atualiza textos do cartão
            txt_saldo.value = f"R$ {formatar_moeda(saldo)}"
            txt_entradas.value = f"R$ {formatar_moeda(entradas)}"
            txt_saidas.value = f"R$ {formatar_moeda(saidas)}"
            
            # Muda a cor do saldo se estiver negativo
            txt_saldo.color = "#4ade80" if saldo >= 0 else "#f87171"
            
            # Reconstrói a lista de transações
            coluna_lancamentos.controls.clear()
            if not user_data["transacoes"]:
                coluna_lancamentos.controls.append(
                    ft.Container(
                        content=ft.Text("Nenhuma conta registrada.", color="grey", italic=True),
                        alignment=ft.alignment.center, padding=20
                    )
                )
            else:
                # Inverte a lista para mostrar os mais recentes primeiro
                for item in reversed(user_data["transacoes"]):
                    cor = "#f87171" if item["tipo"] == "saida" else "#4ade80"
                    sinal = "-" if item["tipo"] == "saida" else "+"
                    icone_tipo = ft.icons.arrow_downward if item["tipo"] == "saida" else ft.icons.arrow_upward
                    
                    card = ft.Container(
                        padding=12, bgcolor="#1e293b", border_radius=12,
                        content=ft.Row([
                            ft.Row([
                                ft.Container(
                                    content=ft.Icon(icone_tipo, color=cor, size=16),
                                    padding=8, bgcolor="#0f172a", border_radius=8
                                ),
                                ft.Column([
                                    ft.Text(item["nome"], color="white", weight="bold"),
                                    ft.Text(item["data"], size=10, color="grey")
                                ], spacing=2)
                            ]),
                            ft.Row([
                                ft.Text(f"{sinal} {formatar_moeda(item['valor'])}", color=cor, weight="bold"),
                                # Botão Deletar
                                ft.IconButton(
                                    ft.icons.DELETE_OUTLINE, 
                                    icon_color="grey", 
                                    icon_size=20, 
                                    data=item["id"], 
                                    tooltip="Remover",
                                    on_click=deletar_item
                                )
                            ])
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                    )
                    coluna_lancamentos.controls.append(card)
            
            page.update()

        # Ação de Deletar
        def deletar_item(e):
            id_rem = e.control.data
            for item in user_data["transacoes"]:
                if item["id"] == id_rem:
                    user_data["transacoes"].remove(item)
                    break
            
            atualizar_dados() # Recalcula tudo
            page.show_snack_bar(ft.SnackBar(ft.Text("Item removido da lista interna."), bgcolor="#334155"))

        # --- Modais de Adicionar (Para tornar o app funcional) ---
        input_nome = ft.TextField(label="Descrição", border_color="#334155")
        input_val = ft.TextField(label="Valor", border_color="#334155", keyboard_type=ft.KeyboardType.NUMBER)
        
        def salvar_transacao(tipo):
            if not input_nome.value or not input_val.value:
                return
            try:
                val_float = float(input_val.value.replace(",", "."))
                new_id = int(time.time()) # ID único baseado no tempo
                user_data["transacoes"].append({
                    "id": new_id,
                    "nome": input_nome.value,
                    "valor": val_float,
                    "tipo": tipo,
                    "data": "Hoje"
                })
                input_nome.value = ""
                input_val.value = ""
                page.close(bs_add)
                atualizar_dados()
                page.show_snack_bar(ft.SnackBar(ft.Text("Lançamento salvo!")))
            except:
                page.show_snack_bar(ft.SnackBar(ft.Text("Valor inválido.")))

        # BottomSheet (Menu inferior para adicionar)
        bs_add = ft.BottomSheet(
            ft.Container(
                padding=20, bgcolor="#1e293b",
                content=ft.Column([
                    ft.Text("Novo Lançamento", weight="bold"),
                    input_nome,
                    input_val,
                    ft.Row([
                        ft.ElevatedButton("Receita (+)", bgcolor="#4ade80", color="black", expand=True, on_click=lambda e: salvar_transacao("entrada")),
                        ft.ElevatedButton("Despesa (-)", bgcolor="#f87171", color="black", expand=True, on_click=lambda e: salvar_transacao("saida")),
                    ])
                ], tight=True)
            )
        )

        # Modal Agendar (Google Agenda)
        input_agenda_nome = ft.TextField(label="Conta", border_color="#334155")
        input_agenda_val = ft.TextField(label="Valor", border_color="#334155", keyboard_type=ft.KeyboardType.NUMBER)
        dialog_agenda = ft.AlertDialog(
            title=ft.Text("Agendar Pagamento"),
            content=ft.Column([ft.Text("Será criado um lembrete na sua agenda.", size=12, color="grey"), input_agenda_nome, input_agenda_val], height=120),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: page.close(dialog_agenda)),
                ft.ElevatedButton("Abrir Agenda", bgcolor="#fbbf24", color="black", on_click=lambda e: [page.close(dialog_agenda), abrir_google_agenda(input_agenda_nome.value, input_agenda_val.value)])
            ], bgcolor="#1e293b"
        )

        # --- Montagem Visual do Dashboard ---
        
        # 1. Header Navigation
        header = ft.Row([
            ft.IconButton(ft.icons.ARROW_BACK, icon_color="white", on_click=lambda e: show_user_selection()),
            ft.Column([
                ft.Text("Gerenciando", size=10, color="grey", text_align=ft.TextAlign.RIGHT),
                ft.Text(user_data["nome"], size=16, weight="bold", color="white")
            ], horizontal_alignment=ft.CrossAxisAlignment.END)
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        # 2. Cartão de Saldo Inteligente
        card_resumo = ft.Container(
            content=ft.Column([
                ft.Text("Saldo em Caixa", color="white70"),
                txt_saldo,
                ft.Divider(color="white10", height=15),
                ft.Row([
                    ft.Column([ft.Row([ft.Icon(ft.icons.ARROW_DOWNWARD, color="#f87171", size=14), ft.Text("Saídas", size=12, color="white70")]), txt_saidas]),
                    ft.Column([ft.Row([ft.Icon(ft.icons.ARROW_UPWARD, color="#4ade80", size=14), ft.Text("Entradas", size=12, color="white70")]), txt_entradas])
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            ]),
            gradient=ft.LinearGradient(colors=["#1e293b", "#0f172a"], begin=ft.alignment.top_left, end=ft.alignment.bottom_right),
            border=ft.border.all(1, "#334155"), border_radius=20, padding=25,
            shadow=ft.BoxShadow(blur_radius=15, color=ft.colors.with_opacity(0.2, "black"))
        )

        # 3. Botões de Ação
        def action_btn(icon, text, color, func):
            return ft.Container(
                content=ft.Column([
                    ft.Container(content=ft.Icon(icon, color=color), padding=12, bgcolor="#1e293b", border_radius=12, border=ft.border.all(1, "#334155")),
                    ft.Text(text, size=10, color="grey")
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                on_click=func
            )

        actions = ft.Row([
            action_btn(ft.icons.ADD, "Novo", "#4ade80", lambda e: page.open(bs_add)),
            action_btn(ft.icons.NOTIFICATION_ADD, "Agendar", "#fbbf24", lambda e: page.open(dialog_agenda)),
            action_btn(ft.icons.PIE_CHART, "Gráfico", "#60a5fa", lambda e: page.show_snack_bar(ft.SnackBar(ft.Text("Em breve...")))),
        ], alignment=ft.MainAxisAlignment.SPACE_AROUND)

        # 4. Lista
        layout = ft.Column([
            ft.Container(height=10),
            header,
            ft.Container(height=20),
            card_resumo,
            ft.Container(height=25),
            actions,
            ft.Container(height=25),
            ft.Text("Histórico Recente", weight="bold", color="white"),
            ft.Container(height=10),
            coluna_lancamentos
        ], scroll=ft.ScrollMode.HIDDEN, expand=True)

        # Inicializa os dados na tela
        atualizar_dados()
        page.add(ft.Container(layout, padding=20, expand=True))


    # --- 5. TELA: Seleção de Usuários ---
    def show_user_selection():
        page.clean()
        
        # Modal criar usuário
        input_new_user = ft.TextField(label="Nome", border_color="#334155")
        def criar_user(e):
            if input_new_user.value:
                users_db.append({"id": len(users_db)+1, "nome": input_new_user.value, "transacoes": []})
                page.close(dialog_new_user)
                show_user_selection()
        
        dialog_new_user = ft.AlertDialog(
            title=ft.Text("Novo Perfil"),
            content=input_new_user,
            actions=[ft.ElevatedButton("Salvar", bgcolor="#00d4ff", color="black", on_click=criar_user)],
            bgcolor="#1e293b"
        )

        # Lista de perfis
        lista_users = ft.Column(spacing=15)
        for user in users_db:
            # Calcula saldo rápido para mostrar no card
            _, _, saldo_prev = calcular_resumo(user)
            card = ft.Container(
                content=ft.Row([
                    ft.Row([
                        ft.CircleAvatar(content=ft.Text(user["nome"][0].upper()), bgcolor="#00d4ff", color="black"),
                        ft.Column([
                            ft.Text(user["nome"], weight="bold", color="white"),
                            ft.Text(f"Saldo: R$ {formatar_moeda(saldo_prev)}", size=12, color="grey")
                        ], spacing=2)
                    ]),
                    ft.Icon(ft.icons.CHEVRON_RIGHT, color="grey")
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                padding=20, bgcolor="#1e293b", border_radius=15, border=ft.border.all(1, "#334155"),
                on_click=lambda e, u=user: show_dashboard(u)
            )
            lista_users.controls.append(card)

        page.add(ft.Container(
            content=ft.Column([
                ft.Row([ft.Text("Perfis", size=24, weight="bold", color="white"), ft.IconButton(ft.icons.EXIT_TO_APP, icon_color="red", on_click=lambda e: show_login())], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Container(height=20),
                lista_users,
                ft.Container(height=20),
                ft.ElevatedButton("Criar Novo Perfil", icon=ft.icons.ADD, bgcolor="#00d4ff", color="black", width=300, on_click=lambda e: page.open(dialog_new_user))
            ]),
            padding=20, expand=True
        ))


    # --- 6. TELA: Login (Admin) ---
    def show_login():
        page.clean()
        user_input = ft.TextField(label="Usuário Admin", color="white", width=280, border_color="#334155")
        
        def login(e):
            if user_input.value: # Aceita qualquer coisa para teste, ou force "admin"
                btn_entrar.content = ft.ProgressRing(width=20, height=20, color="black")
                btn_entrar.update()
                time.sleep(0.5)
                show_user_selection()
            else:
                user_input.error_text = "Digite um usuário"
                user_input.update()

        btn_entrar = ft.ElevatedButton("ACESSAR GESTÃO", bgcolor="#00d4ff", color="black", width=280, height=50, on_click=login)
        
        page.add(ft.Container(
            content=ft.Column([
                ft.Icon(ft.icons.SECURITY, size=60, color="#00d4ff"),
                ft.Text("ANDY MANAGER", weight="bold", size=22, color="white"),
                ft.Container(height=30),
                user_input,
                ft.Container(height=10),
                btn_entrar
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True, alignment=ft.alignment.center,
            gradient=ft.LinearGradient(colors=["#0f172a", "#000000"], begin=ft.alignment.top_center, end=ft.alignment.bottom_center)
        ))

    show_login()

ft.app(target=main)
