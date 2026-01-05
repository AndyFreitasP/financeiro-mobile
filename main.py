import flet as ft

def main(page: ft.Page):
    # Configuração de Segurança
    page.title = "Andy Financeiro"
    page.bgcolor = "#0f172a" # Azul escuro (Se você ver essa cor, o app carregou)
    page.padding = 20
    page.theme_mode = ft.ThemeMode.DARK
    
    # Se o teclado abrir, a tela rola para não cobrir o input
    page.scroll = ft.ScrollMode.ADAPTIVE

    # Feedback simples
    def login_click(e):
        if not user_input.value:
            user_input.error_text = "Preencha o usuário"
            user_input.update()
        else:
            btn_entrar.text = "ENTRANDO..."
            btn_entrar.disabled = True
            btn_entrar.update()
            
            page.snack_bar = ft.SnackBar(ft.Text(f"Bem-vindo, {user_input.value}!"))
            page.snack_bar.open = True
            page.update()

    # Elementos visuais nativos (Sem imagens externas)
    logo_icon = ft.Icon(
        name=ft.icons.ACCOUNT_BALANCE_WALLET, 
        size=80, 
        color=ft.colors.BLUE_200
    )
    
    title_text = ft.Text(
        "Andy Financeiro", 
        size=28, 
        weight=ft.FontWeight.BOLD,
        color="white"
    )

    user_input = ft.TextField(
        label="Usuário",
        border_color="white54",
        width=300,
    )

    password_input = ft.TextField(
        label="Senha",
        password=True,
        can_reveal_password=True,
        border_color="white54",
        width=300,
    )

    btn_entrar = ft.ElevatedButton(
        text="ACESSAR SISTEMA",
        bgcolor=ft.colors.BLUE_600,
        color="white",
        width=300,
        height=50,
        on_click=login_click
    )

    # Container Centralizado
    login_card = ft.Container(
        content=ft.Column(
            controls=[
                logo_icon,
                ft.Divider(height=20, color="transparent"),
                title_text,
                ft.Divider(height=40, color="transparent"),
                user_input,
                ft.Divider(height=10, color="transparent"),
                password_input,
                ft.Divider(height=30, color="transparent"),
                btn_entrar
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        alignment=ft.alignment.center,
        padding=20
    )

    page.add(login_card)

# IMPORTANTE: Removi o assets_dir para este teste
ft.app(target=main)
