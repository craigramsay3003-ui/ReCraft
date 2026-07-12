# Architecture

## UI layer

`recraft.ui` owns desktop interaction and image presentation. It asks the registry for style metadata and parameter definitions, so it contains no style-specific processing rules.

## Processing layer

`recraft.core` loads and normalises images. Each processor accepts a Pillow image plus a parameter mapping and returns a new Pillow image. This API is usable by future batch and command-line tools without starting the UI.

## Style plugin system

`ArtStyle` defines the contract: identifier, display name, description, parameters, validation, and processing. `StyleRegistry` stores unique styles and supplies them to clients.

To add a style, create a module in `recraft.styles`, subclass `ArtStyle`, define its parameter metadata and processor, and add an instance to `create_default_registry`. The UI will discover it automatically.

## Future exporters and mesh generation

Exporters should consume processing results without depending on the UI. Vector exporters can initially consume style-specific paths, while a later geometry layer can translate depth maps or procedural primitives into validated meshes. Keeping these layers separate prevents manufacturing concerns from complicating image interpretation.
