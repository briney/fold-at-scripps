import { useMemo, useState, type JSX } from "react";

import { Link } from "react-router-dom";

import EmptyState from "@/components/states/EmptyState";
import ErrorState from "@/components/states/ErrorState";
import Loading from "@/components/states/Loading";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useTools } from "@/hooks/use-tools";
import type { ToolSummary } from "@/types/api";

function matchesQuery(tool: ToolSummary, query: string): boolean {
  const haystack = `${tool.name} ${tool.description ?? ""}`.toLowerCase();
  return haystack.includes(query);
}

function groupByCategory(tools: ToolSummary[]): [string, ToolSummary[]][] {
  const groups = new Map<string, ToolSummary[]>();
  for (const tool of tools) {
    const bucket = groups.get(tool.category);
    if (bucket) bucket.push(tool);
    else groups.set(tool.category, [tool]);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

interface ToolCardProps {
  tool: ToolSummary;
}

function ToolCard({ tool }: ToolCardProps): JSX.Element {
  return (
    <Link
      to={`/tools/${tool.id}`}
      className="block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <Card className="h-full transition-colors hover:border-primary">
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle>{tool.name}</CardTitle>
            <Badge variant="outline">v{tool.version}</Badge>
          </div>
          {tool.description ? <CardDescription>{tool.description}</CardDescription> : null}
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          <Badge variant="secondary">
            {tool.gpu_count} GPU{tool.gpu_count === 1 ? "" : "s"}
          </Badge>
          {tool.supports_batch ? <Badge variant="secondary">Batch</Badge> : null}
        </CardContent>
      </Card>
    </Link>
  );
}

/** Researcher-facing catalog of runnable tools with search and category grouping. */
export default function CatalogPage(): JSX.Element {
  const { data, isLoading, isError, refetch } = useTools();
  const [query, setQuery] = useState("");

  const groups = useMemo(() => {
    const tools = data ?? [];
    const normalized = query.trim().toLowerCase();
    const filtered = normalized ? tools.filter((tool) => matchesQuery(tool, normalized)) : tools;
    return groupByCategory(filtered);
  }, [data, query]);

  function handleQueryChange(event: React.ChangeEvent<HTMLInputElement>): void {
    setQuery(event.target.value);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Tools</h1>
        <p className="text-sm text-muted-foreground">Browse and launch available tools.</p>
      </div>

      <div className="max-w-sm space-y-2">
        <Label htmlFor="tool-search">Search tools</Label>
        <Input
          id="tool-search"
          type="search"
          placeholder="Search tools"
          value={query}
          onChange={handleQueryChange}
        />
      </div>

      {isLoading ? (
        <Loading label="Loading tools" />
      ) : isError ? (
        <ErrorState message="Failed to load tools." onRetry={() => void refetch()} />
      ) : groups.length === 0 ? (
        <EmptyState
          title="No tools found"
          description="Nothing matches your search. Try a different term."
        />
      ) : (
        <div className="space-y-8">
          {groups.map(([category, tools]) => (
            <section key={category} className="space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                {category}
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {tools.map((tool) => (
                  <ToolCard key={tool.id} tool={tool} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
