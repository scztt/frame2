"""
Configuration deserialization for reactive systems.

Parses YAML/dict configs with three sections:
- sources: Data producers with optional target connections
- model: State dictionary with optional inline sources/effects
- effects: Side effects with optional source connections

Supports @ references for connecting components and inline definitions
for simpler configs.
"""

from typing import Any, Dict, List, Tuple
from frame.action_observable import Model, PropertyAction, ReplaceAction, make_source, make_effect


class ConfigError(Exception):
    """Raised when config is invalid."""

    pass


class ReactiveConfig:
    """
    Parsed reactive configuration with sources, model, and effects.

    Handles three-phase initialization:
    1. Parse sections and build catalogs
    2. Build initial model state
    3. Resolve @ references and create subscriptions
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize from config dict.

        Args:
            config: Dict with 'sources', 'model', and/or 'effects' sections
        """
        self.config = config

        # Catalogs of created instances
        self.sources_catalog: Dict[str, Any] = {}
        self.effects_catalog: Dict[str, Any] = {}
        self.model_state: Dict[str, Any] = {}

        # Track connections to make
        self.connections: List[Tuple[str, str, str]] = []  # (from_type, from_name, to_name)

        # The final model
        self.model: Model = None

    def build(self) -> Model:
        """
        Build the complete reactive system from config.

        Returns:
            Configured Model instance with all connections set up
        """
        # Phase 1: Parse sections
        self._parse_sources()
        self._parse_model()
        self._parse_effects()

        # Phase 2: Create model with initial state
        self.model = Model(self.model_state)

        # Phase 3: Resolve references and connect
        self._connect_all()

        return self.model

    def _parse_sources(self):
        """Parse sources section and build sources catalog."""
        sources_config = self.config.get("sources", {})

        for source_name, source_settings in sources_config.items():
            # Handle target field
            if "target" in source_settings:
                target = source_settings["target"]

                # Validate: target must be string or list, not object
                if isinstance(target, dict):
                    raise ConfigError(f"Source '{source_name}' has object as target - " f"only model items can have inline objects")

                # Handle single target or list of targets
                if isinstance(target, str):
                    targets = [target]
                elif isinstance(target, list):
                    targets = target
                else:
                    raise ConfigError(f"Source '{source_name}' target must be string or list, got {type(target)}")

                # Store connections for each target
                for target_name in targets:
                    self.connections.append(("source", source_name, target_name))

            # Create source (remove target from settings for make_source)
            source_settings_copy = {k: v for k, v in source_settings.items() if k != "target"}
            source, _ = make_source(source_settings_copy)
            self.sources_catalog[source_name] = source

    def _parse_model(self):
        """Parse model section and build model state + inline sources/effects."""
        model_config = self.config.get("model", {})

        for field_name, field_settings in model_config.items():
            # Get initial value (default to None)
            if isinstance(field_settings, dict):
                initial_value = field_settings.get("default", None)
            else:
                initial_value = field_settings

            self.model_state[field_name] = initial_value

            # Handle inline source
            if isinstance(field_settings, dict) and "source" in field_settings:
                source_def = field_settings["source"]

                # Validate: inline source cannot have target
                if isinstance(source_def, dict) and "target" in source_def:
                    raise ConfigError(f"Model item '{field_name}' has inline source with 'target' field - " f"this conflicts with the model item being the implicit target")

                # Create inline source
                inline_source_name = f"{field_name}(source)"
                source, _ = make_source(source_def)
                self.sources_catalog[inline_source_name] = source

                # Connect inline source to this model field
                self.connections.append(("source", inline_source_name, field_name))

            # Handle inline or referenced effect
            if isinstance(field_settings, dict) and "effect" in field_settings:
                effect_def = field_settings["effect"]

                if isinstance(effect_def, str):
                    # Reference to named effect
                    effect_name = effect_def
                    self.connections.append(("model", field_name, effect_name))
                elif isinstance(effect_def, dict):
                    # Inline effect definition

                    # Validate: inline effect cannot have source
                    if "source" in effect_def:
                        raise ConfigError(f"Model item '{field_name}' has inline effect with 'source' field - " f"this conflicts with the model item being the implicit source")

                    # Create inline effect
                    inline_effect_name = f"{field_name}(effect)"
                    effect, _ = make_effect(effect_def)
                    self.effects_catalog[inline_effect_name] = effect

                    # Connect this model field to inline effect
                    self.connections.append(("model", field_name, inline_effect_name))
                else:
                    raise ConfigError(f"Model item '{field_name}' effect must be @reference or dict, got {type(effect_def)}")

    def _parse_effects(self):
        """Parse effects section and build effects catalog."""
        effects_config = self.config.get("effects", {})

        for effect_name, effect_settings in effects_config.items():
            # Check for source reference
            if "source" in effect_settings:
                source_ref = effect_settings["source"]
                if isinstance(source_ref, str):
                    # String references model field
                    model_item = source_ref
                    self.connections.append(("model", model_item, effect_name))
                elif isinstance(source_ref, dict):
                    raise ConfigError(f"Effect '{effect_name}' has inline source object - " f"effects section cannot contain nested objects")
                elif isinstance(source_ref, list):
                    # List of model fields
                    for field in source_ref:
                        self.connections.append(("model", field, effect_name))

            # Create effect (remove source from settings)
            effect_settings_copy = {k: v for k, v in effect_settings.items() if k != "source"}
            effect, _ = make_effect(effect_settings_copy)
            self.effects_catalog[effect_name] = effect

    def _connect_all(self):
        """Resolve all @ references and create subscriptions."""
        for from_type, from_name, to_name in self.connections:
            if from_type == "source":
                # Source -> Model field
                self._connect_source_to_model(from_name, to_name)
            elif from_type == "model":
                # Model field -> Effect
                self._connect_model_to_effect(from_name, to_name)

    def _connect_source_to_model(self, source_name: str, model_field: str):
        """
        Connect source to model field.

        Args:
            source_name: Name in sources catalog
            model_field: Field name in model state
        """
        if source_name not in self.sources_catalog:
            raise ConfigError(f"Source '{source_name}' not found in sources catalog")

        if model_field not in self.model_state:
            raise ConfigError(f"Model field '{model_field}' not found in model state")

        source = self.sources_catalog[source_name]

        # Subscribe: when source emits, update model field
        def update_model(result):
            self.model.emit(PropertyAction(model_field, ReplaceAction(result)))

        source.subscribe(update_model)

    def _connect_model_to_effect(self, model_field: str, effect_name: str):
        """
        Connect model field to effect.

        Args:
            model_field: Field name in model state
            effect_name: Name in effects catalog
        """
        if model_field not in self.model_state:
            raise ConfigError(f"Model field '{model_field}' not found in model state")

        if effect_name not in self.effects_catalog:
            raise ConfigError(f"Effect '{effect_name}' not found in effects catalog")

        effect = self.effects_catalog[effect_name]

        # Subscribe effect to model changes
        # Effect receives the full new state
        def on_model_change(new_state):
            effect(new_state)

        self.model.subscribe(on_model_change)


def load_config(config: Dict[str, Any]) -> Model:
    """
    Load reactive system from config dict.

    Args:
        config: Dict with 'sources', 'model', and/or 'effects' sections

    Returns:
        Configured Model instance

    Example:
        config = {
            "model": {
                "temperature": {
                    "default": 20,
                    "source": {"type": "shell", "command": "sensors"},
                    "effect": {"type": "file_write", "path": "/tmp/temp.txt", "template": "{{ temperature }}"}
                }
            }
        }
        model = load_config(config)
    """
    reactive_config = ReactiveConfig(config)
    return reactive_config.build()
