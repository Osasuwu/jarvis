"""Simple echo tool for testing and demonstration."""

from jarvis.tools.base import RiskLevel, Tool, ToolParameter, ToolResult


class EchoTool(Tool):
    """
    Simple tool that echoes back the input.
    Useful for testing the orchestrator and tool system.
    """

    name = "echo"
    description = "Echo back the provided text. Useful for testing."
    risk_level = RiskLevel.LOW
    requires_confirmation = False
    capabilities = ["utility", "test"]

    async def execute(self, **kwargs) -> ToolResult:
        """
        Echo the input text.

        Args:
            **kwargs: Must contain 'text' parameter

        Returns:
            ToolResult with echoed text
        """
        text = kwargs.get("text", "")
        prefix = kwargs.get("prefix", "Echo:")

        output = f"{prefix} {text}"

        return ToolResult(
            success=True,
            output=output,
        )

    def get_parameters(self) -> list[ToolParameter]:
        """Get tool parameters."""
        return [
            ToolParameter(
                name="text",
                type="string",
                description="Text to echo back",
                required=True,
            ),
            ToolParameter(
                name="prefix",
                type="string",
                description="Optional prefix for the echoed text",
                required=False,
                default="Echo:",
            ),
        ]
