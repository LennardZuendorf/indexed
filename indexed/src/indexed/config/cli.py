"""Config command for managing index configuration."""

import typer
from core.v1 import Config

app = typer.Typer(help="Manage configuration")

@app.command("inspect")
def inspect():
    """Display current configuration."""
    config = Config.load()
    typer.echo(config.pretty_print())


@app.command("init")
def init(
    embedding_model: str = typer.Option(None, "--model", "-m", help="Embedding model"),
    chunk_size: int = typer.Option(None, "--chunk-size", help="Chunk size"),
    storage_path: str = typer.Option(None, "--storage", "-s", help="Storage path"),
):
    """Initialize a new configuration."""
    kwargs = {}
    if embedding_model:
        kwargs["embedding_model"] = embedding_model
    if chunk_size:
        kwargs["chunk_size"] = chunk_size
    if storage_path:
        kwargs["storage_path"] = storage_path
    
    config = Config(**kwargs)
    config.save()
    typer.echo("✓ Configuration initialized")
    typer.echo("\n" + config.pretty_print())


@app.command("set")
def set_config(
    key: str = typer.Argument(..., help="Configuration key to set"),
    value: str = typer.Argument(..., help="Value to set"),
):
    """Set a configuration value.
    
    Examples:
        indexed config set embedding_model all-MiniLM-L6-v2
        indexed config set chunk_size 512
        indexed config set storage_path /path/to/storage
    """
    config = Config.load()
    
    # Map string keys to actual config attributes
    key_mapping = {
        "embedding_model": "embedding_model",
        "chunk_size": "chunk_size", 
        "storage_path": "storage_path",
        "model": "embedding_model",  # alias
        "storage": "storage_path",  # alias
    }
    
    if key not in key_mapping:
        typer.echo(f"❌ Error: Unknown configuration key '{key}'", err=True)
        typer.echo("Available keys: embedding_model, chunk_size, storage_path", err=True)
        raise typer.Exit(1)
    
    attr_name = key_mapping[key]
    
    # Convert value to appropriate type
    if attr_name == "chunk_size":
        try:
            int_value = int(value)
        except ValueError:
            typer.echo(f"❌ Error: chunk_size must be an integer, got '{value}'", err=True)
            raise typer.Exit(1)
        setattr(config, attr_name, int_value)
    else:
        setattr(config, attr_name, value)
    
    config.save()
    typer.echo(f"✓ Set {key} = {value}")


@app.command("validate")
def validate():
    """Validate current configuration.
    
    Checks that all required configuration values are set and valid.
    """
    try:
        config = Config.load()
        
        # Check required fields
        required_fields = ["embedding_model", "chunk_size", "storage_path"]
        missing_fields = []
        
        for field in required_fields:
            if not hasattr(config, field) or getattr(config, field) is None:
                missing_fields.append(field)
        
        if missing_fields:
            typer.echo("❌ Configuration validation failed:", err=True)
            for field in missing_fields:
                typer.echo(f"  • Missing required field: {field}", err=True)
            typer.echo("\nRun 'indexed config init' to set up configuration", err=True)
            raise typer.Exit(1)
        
        # Check chunk_size is positive
        if config.chunk_size <= 0:
            typer.echo("❌ Configuration validation failed:", err=True)
            typer.echo(f"  • chunk_size must be positive, got {config.chunk_size}", err=True)
            raise typer.Exit(1)
        
        typer.echo("✓ Configuration is valid")
        
    except Exception as e:
        typer.echo(f"❌ Error validating configuration: {e}", err=True)
        raise typer.Exit(1)


@app.command("reset")
def reset():
    """Reset configuration to defaults.
    
    This will create a new configuration with default values.
    """
    if not typer.confirm("Reset configuration to defaults? This will overwrite current settings."):
        typer.echo("Cancelled")
        raise typer.Exit(0)
    
    try:
        # Create new config with default values
        config = Config()  # This creates a new instance with default values
        config.save()
        
        typer.echo("✓ Configuration reset to defaults")
        typer.echo("\n" + config.pretty_print())
        
    except Exception as e:
        typer.echo(f"❌ Error resetting configuration: {e}", err=True)
        raise typer.Exit(1)
