import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@testing-library/react";
import { vi } from "vitest";
import SchemaForm from "@/lib/schema-form/SchemaForm";
import type { ToolRead } from "@/types/api";
import ablang2 from "./__fixtures__/ablang2.json";
import antifold from "./__fixtures__/antifold.json";

function tool(): ToolRead {
  return {
    id: "t1",
    name: "antifold",
    version: "1.0.0",
    category: "inverse-folding",
    gpu_count: 1,
    description: "d",
    supports_batch: false,
    image_tag: "antifold:1",
    default_timeout: 600,
    input_schema: antifold as ToolRead["input_schema"],
  };
}

function ablang2Tool(): ToolRead {
  return {
    id: "t2",
    name: "ablang2",
    version: "1.0.0",
    category: "antibody-lm",
    gpu_count: 1,
    description: "d",
    supports_batch: false,
    image_tag: "ablang2:1",
    default_timeout: 600,
    input_schema: ablang2 as ToolRead["input_schema"],
  };
}

test("renders required structure_path up top and hides advanced fields until expanded", () => {
  render(<SchemaForm tool={tool()} onSubmit={vi.fn()} />);
  expect(screen.getByLabelText(/structure path/i)).toBeInTheDocument();
  // num_sequences is optional/defaulted -> inside Advanced, not visible initially
  expect(screen.queryByLabelText(/num sequences/i)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /advanced options/i })).toBeInTheDocument();
});

test("shows a required JSON/array field up top without expanding Advanced", () => {
  render(<SchemaForm tool={ablang2Tool()} onSubmit={vi.fn()} />);
  // ablang2's required `sequences` is an array-of-objects -> json kind. It must
  // be visible immediately, not hidden inside the collapsed Advanced panel.
  expect(screen.getByLabelText(/sequences/i)).toBeInTheDocument();
});

test("uploads a file and submits values + files", async () => {
  const onSubmit = vi.fn();
  render(<SchemaForm tool={tool()} onSubmit={onSubmit} />);
  const file = new File(["ATOM"], "backbone.pdb", { type: "chemical/x-pdb" });
  await userEvent.upload(screen.getByLabelText(/structure path/i), file);
  await userEvent.click(screen.getByRole("button", { name: /submit/i }));
  expect(onSubmit).toHaveBeenCalledTimes(1);
  const arg = onSubmit.mock.calls[0][0];
  expect(arg.files.map((f: File) => f.name)).toEqual(["backbone.pdb"]);
  expect(arg.values.structure_path).toBe("backbone.pdb");
});

test("an object field renders a JSON editor and rejects invalid JSON", async () => {
  const onSubmit = vi.fn();
  render(<SchemaForm tool={tool()} onSubmit={onSubmit} />);
  await userEvent.click(screen.getByRole("button", { name: /advanced options/i }));
  const jsonEditor = screen.getByLabelText(/fixed positions/i);
  // `{` is a special char in userEvent.type; `{{` types a literal `{`.
  await userEvent.type(jsonEditor, "{{not json");
  await userEvent.upload(screen.getByLabelText(/structure path/i), new File(["A"], "b.pdb"));
  await userEvent.click(screen.getByRole("button", { name: /submit/i }));
  expect(onSubmit).not.toHaveBeenCalled();
  expect(await screen.findByText(/valid json/i)).toBeInTheDocument();
});
