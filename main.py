import flet as ft

def main(page: ft.Page):
    # 1. Configuração Visual (Tema Dark)
    page.title = "Andy Financeiro"
    page.padding = 0
    page.theme_mode = ft.ThemeMode.DARK
    
    # 2. Lógica de Interação
    def login_click(e):
        if not user_input.value:
            user_input.error_text = "Campo obrigatório"
            user_input.update()
        else:
            # Feedback de carregamento no botão
            btn_entrar.content = ft.ProgressRing(width=20, height=20, color="black", stroke_width=2)
            btn_entrar.update()
            
            # Simulação de acesso
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Conectando ao cofre de {user_input.value}..."),
                bgcolor="#00d4ff",
                content_color="black"
            )
            page.snack_bar.open = True
            page.update()

    # 3. Componentes da Interface (Design High-End sem Imagens)
    
    # Ícone Principal (Substitui a imagem que estava travando)
    logo_icon = ft.Container(
        content=ft.Icon(ft.icons.SHIELD_MOON, size=60, color="#00d4ff"),
        padding=20,
        bgcolor=ft.colors.with_opacity(0.1, "#00d4ff"),
        border_radius=50, # Círculo perfeito
        border=ft.border.all(1, "#00d4ff")
    )

    user_input = ft.TextField(
        label="ID de Usuário",
        border_color="#374151",
        focused_border_color="#00d4ff",
        text_style=ft.TextStyle(color="white"),
        label_style=ft.TextStyle(color="grey"),
        prefix_icon=ft.icons.PERSON_OUTLINE,
        width=280,
    )

    password_input = ft.TextField(
        label="Senha de Acesso",
        password=True,
        can_reveal_password=True,
        border_color="#374151",
        focused_border_color="#00d4ff",
        text_style=ft.TextStyle(color="white"),
        label_style=ft.TextStyle(color="grey"),
        prefix_icon=ft.icons.LOCK_OUTLINE,
        width=280,
    )

    btn_entrar = ft.ElevatedButton(
        content=ft.Text("ACESSAR SISTEMA", color="black", weight="bold"),
        bgcolor="#00d4ff", # Azul Neon
        width=280,
        height=50,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            elevation=10,
        ),
        on_click=login_click
    )

    footer = ft.Text(
        "Secure System v1.0", 
        size=10, 
        color=ft.colors.with_opacity(0.3, "white")
    )

    # 4. O Cartão Central (Container Seguro)
    card_login = ft.Container(
        content=ft.Column(
            [
                logo_icon,
                ft.Text("ANDY FINANCEIRO", size=22, weight="bold", color="white"),
                ft.Divider(height=20, color="transparent"),
                user_input,
                password_input,
                ft.Divider(height=20, color="transparent"),
                btn_entrar,
                ft.Divider(height=10, color="transparent"),
                footer
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=15
        ),
        width=340,
        padding=40,
        border_radius=20,
        bgcolor="#111827", # Fundo do cartão sólido
        border=ft.border.all(1, "#1f2937"),
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=20,
            color=ft.colors.with_opacity(0.4, "black"),
            offset=ft.Offset(0, 10),
        )
    )

    # 5. Fundo Gradiente (Substitui a imagem de fundo)
    # Isso roda na GPU nativa, zero risco de arquivo não encontrado.
    background = ft.Container(
        expand=True,
        gradient=ft.LinearGradient(
            begin=ft.alignment.top_center,
            end=ft.alignment.bottom_center,
            colors=["#0f172a", "#000000"], # Azul escuro para Preto
        )
    )

    # Montagem Final
    page.add(
        ft.Stack(
            controls=[
                background,
                ft.Container(
                    content=card_login,
                    alignment=ft.alignment.center,
                    expand=True
                )
            ],
            expand=True
        )
    )

# NÃO use assets_dir aqui, pois removemos as imagens para garantir compatibilidade.
ft.app(target=main)
