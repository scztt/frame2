import typer
import uvicorn
import os

app_cli = typer.Typer()


@app_cli.command()
def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    config: str = "src/frame/examples/example_config.yaml",
):
    """Run the FastAPI server

    Args:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 8000)
        config: Path to YAML config file (default: src/frame/examples/example_config.yaml)
    """
    # Set environment variable - will be inherited by uvicorn subprocess
    os.environ["FRAME_CONFIG_PATH"] = config

    typer.echo(f"🚀 Starting server with config: {config}")
    typer.echo(f"   Environment variable set: FRAME_CONFIG_PATH={config}")

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
