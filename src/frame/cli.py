import typer
import uvicorn

app_cli = typer.Typer()


@app_cli.command()
def run_server(host: str = "127.0.0.1", port: int = 8000):
    """Run the FastAPI server"""
    uvicorn.run("frame.main:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    app_cli()
