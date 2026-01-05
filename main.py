import flet as ft

def main(page: ft.Page):
    # 1. Configuração da Janela
    page.title = "Andy Financeiro"
    page.bgcolor = "#1f2937"  # Cinza Chumbo (Para você ver que não é erro)
    page.padding = 0
    page.theme_mode = ft.ThemeMode.DARK

    # 2. Lógica do Botão
    def login_click(e):
        if not user_input.value:
            user_input.error_text = "Digite seu usuário"
            user_input.update()
        else:
            # Feedback visual de carregamento
            btn_entrar.content = ft.ProgressRing(width=20, height=20, color="black")
            btn_entrar.update()
            
            page.snack_bar = ft.SnackBar(ft.Text(f"Bem-vindo, {user_input.value}!"))
            page.snack_bar.open = True
            page.update()

    # 3. Componentes da UI
    user_input = ft.TextField(
        label="Usuário",
        border_color="#4b5563", # Cinza médio
        text_style=ft.TextStyle(color="white"),
        cursor_color="white",
        width=280,
    )

    password_input = ft.TextField(
        label="Senha",
        password=True,
        can_reveal_password=True,
        border_color="#4b5563",
        text_style=ft.TextStyle(color="white"),
        cursor_color="white",
        width=280,
    )

    btn_entrar = ft.ElevatedButton(
        content=ft.Text("ACESSAR SISTEMA", color="black", weight="bold"),
        bgcolor="#00d4ff", # Azul Cyan (Destaque gótico/tech)
        width=280,
        height=50,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
        on_click=login_click
    )

    # 4. Cartão de Login (Sem Blur para não travar o celular)
    login_card = ft.Container(
        width=320,
        padding=35,
        border_radius=15,
        bgcolor="#111827", # Quase preto, mas visível sobre o fundo
        border=ft.border.all(1, "#374151"),
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=15,
            color=ft.colors.with_opacity(0.5, "black"),
        ),
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20,
            controls=[
                ft.Icon(ft.icons.SHIELD_MOON, size=50, color="#00d4ff"),
                ft.Text("ANDY FINANCEIRO", size=20, weight="bold", color="white"),
                ft.Divider(height=10, color="transparent"),
                user_input,
                password_input,
                ft.Divider(height=20, color="transparent"),
                btn_entrar,
            ]
        )
    )

    # 5. Fundo com Imagem (Com fallback de segurança)
    # A imagem 'icon.png' foi gerada pelo nosso script YAML na pasta assets
    background_image = ft.Image(
        src="icon.png", 
        fit=ft.ImageFit.COVER,
        opacity=0.15,
        expand=True,
        # Se a imagem falhar, não quebra o app, apenas não mostra nada
        error_content=ft.Container(bgcolor="#1f2937") 
    )

    # 6. Montagem Final (Stack)
    page.add(
        ft.Stack(
            expand=True,
            controls=[
                background_image, # Fica no fundo
                ft.Container(     # Fica na frente (centralizado)
                    content=login_card,
                    alignment=ft.alignment.center,
                    expand=True
                )
            ]
        )
    )

# CRUCIAL: assets_dir="assets" diz onde buscar o icon.png
ft.app(target=main, assets_dir="assets")
