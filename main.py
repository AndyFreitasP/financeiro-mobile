import flet as ft


def main(page: ft.Page):
    page.title = "Andy Financeiro"
    page.bgcolor = "#000000"
    page.window_maximized = True

    imagem_fundo = ft.Image(
        src="icone.png",
        fit=ft.ImageFit.CONTAIN,
        opacity=0.05,
        expand=True,
    )

    conteudo = ft.Column(
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(
                "Andy Financeiro",
                size=28,
                weight=ft.FontWeight.BOLD,
                color="white",
            ),
            ft.Text(
                "Powered by AndyP",
                size=12,
                color="white54",
            ),
        ],
    )

    page.add(
        ft.Stack(
            expand=True,
            controls=[
                imagem_fundo,
                conteudo,
            ],
        )
    )


ft.app(target=main)
