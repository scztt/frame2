import typer
import uvicorn

app_cli = typer.Typer()


@app_cli.command()
def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the FastAPI server"""
    uvicorn.run(
        "frame.main:app",
        host=host,
        port=port,
        reload=True,
        reload_includes=["*.yaml", "*.py"],
        reload_dirs=["examples", "src/frame"],
    )


if __name__ == "__main__":
    app_cli()
