import flet as ft

def main(page: ft.Page):
    # Configurações para Mobile
    page.title = "Andy Financeiro"
    page.bgcolor = "#111111" # Cinza muito escuro (menos agressivo que preto puro)
    page.padding = 0
    page.theme_mode = ft.ThemeMode.DARK # Força modo escuro nativo

    # Feedback visual ao clicar
    def login_click(e):
        if not user_input.value:
            user_input.error_text = "Digite o usuário"
            user_input.update()
        else:
            btn_entrar.content = ft.ProgressRing(width=20, height=20, color="black")
            btn_entrar.update()
            # Simulação de login
            page.snack_bar = ft.SnackBar(ft.Text(f"Bem-vindo, {user_input.value}!"))
            page.snack_bar.open = True
            page.update()

    # Campos de Entrada (Otimizados)
    user_input = ft.TextField(
        label="Usuário",
        border_color="#333333",
        text_style=ft.TextStyle(color="white"),
        label_style=ft.TextStyle(color="grey"),
        cursor_color="white",
        width=280,
    )

    password_input = ft.TextField(
        label="Senha",
        password=True,
        can_reveal_password=True,
        border_color="#333333",
        text_style=ft.TextStyle(color="white"),
        label_style=ft.TextStyle(color="grey"),
        cursor_color="white",
        width=280,
    )

    btn_entrar = ft.ElevatedButton(
        content=ft.Text("ACESSAR", color="black"),
        bgcolor="white",
        width=280,
        height=45,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
        on_click=login_click
    )

    # Cartão de Login (SEM BLUR - Leve para o processador)
    login_card = ft.Container(
        width=320,
        padding=30,
        border_radius=20,
        bgcolor="#1A1A1A", # Cor sólida em vez de vidro fosco pesado
        border=ft.border.all(1, "#333333"),
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20,
            controls=[
                ft.Icon(ft.icons.SHIELD_MOON_OUTLINED, size=60, color="white"),
                ft.Text("Andy Financeiro", size=22, weight="bold", color="white"),
                ft.Divider(color="transparent", height=10),
                user_input,
                password_input,
                ft.Divider(color="transparent", height=10),
                btn_entrar,
            ]
        )
    )

    # Imagem de fundo com opacidade baixa (Tratamento de erro simples)
    # A imagem precisa estar na pasta 'assets' criada pelo GitHub Actions
    fundo = ft.Image(
        src="icon.png", # O GitHub renomeou para icon.png na pasta assets
        fit=ft.ImageFit.COVER,
        opacity=0.1,
        expand=True,
        error_content=ft.Container(bgcolor="#111111") # Se falhar, fica cinza
    )

    # Montagem da tela usando Stack
    page.add(
        ft.Stack(
            expand=True,
            controls=[
                fundo,
                ft.Container(
                    expand=True,
                    alignment=ft.alignment.center,
                    content=login_card
                )
            ]
        )
    )

# CRUCIAL: assets_dir="assets" diz ao Android onde buscar as imagens
ft.app(target=main, assets_dir="assets")
