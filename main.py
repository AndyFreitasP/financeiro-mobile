import flet as ft

def main(page: ft.Page):
    page.title = "Andy Financeiro"
    page.bgcolor = "#050505" # Preto absoluto cansa a vista, use um off-black
    page.window_maximized = True
    page.padding = 0
    
    # Validação visual (Feedback para o usuário)
    def login_click(e):
        if not user_input.value:
            user_input.error_text = "Quem é você?"
            user_input.update()
        else:
            page.snack_bar = ft.SnackBar(ft.Text(f"Acessando cofre de {user_input.value}..."))
            page.snack_bar.open = True
            page.update()

    # Elementos de UI
    user_input = ft.TextField(
        label="Usuário",
        border_color="white24",
        text_style=ft.TextStyle(color="white"),
        label_style=ft.TextStyle(color="white54"),
        cursor_color="white",
        width=280,
    )

    password_input = ft.TextField(
        label="Senha",
        password=True,
        can_reveal_password=True,
        border_color="white24",
        text_style=ft.TextStyle(color="white"),
        label_style=ft.TextStyle(color="white54"),
        cursor_color="white",
        width=280,
    )

    btn_entrar = ft.ElevatedButton(
        text="ACESSAR SISTEMA",
        color="black",
        bgcolor="white",
        width=280,
        height=45,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=5),
        ),
        on_click=login_click
    )

    # O "Cartão" Central (Glassmorphism)
    login_card = ft.Container(
        width=350,
        padding=40,
        border_radius=15,
        bgcolor=ft.colors.with_opacity(0.05, ft.colors.WHITE),
        blur=ft.Blur(10, 10), # O efeito de vidro
        border=ft.border.all(1, ft.colors.with_opacity(0.1, ft.colors.WHITE)),
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20,
            controls=[
                ft.Icon(ft.icons.ACCOUNT_BALANCE_WALLET_OUTLINED, size=50, color="white"),
                ft.Text("Andy Financeiro", size=24, weight="bold", color="white"),
                ft.Divider(color="transparent", height=10),
                user_input,
                password_input,
                ft.Divider(color="transparent", height=10),
                btn_entrar,
                ft.Text("v.1.0.0", size=10, color="white24"),
            ]
        )
    )

    # Imagem de fundo (Tratamento de erro se não existir)
    background_stack = [
        ft.Container(expand=True, bgcolor="#000000") # Fundo base caso a imagem falhe
    ]
    
    try:
        background_image = ft.Image(
            src="icone.png",
            fit=ft.ImageFit.COVER, # Cover preenche melhor que Contain
            opacity=0.2,
            expand=True,
        )
        background_stack.append(background_image)
    except:
        pass # Segue sem imagem

    # Montagem da Tela
    background_stack.append(
        ft.Row(
            expand=True,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    expand=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[login_card]
                )
            ]
        )
    )

    page.add(ft.Stack(expand=True, controls=background_stack))

ft.app(target=main)
