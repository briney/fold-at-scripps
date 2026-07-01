import { useId, useMemo, useState, type JSX } from "react";

import EmptyState from "@/components/states/EmptyState";
import ErrorState from "@/components/states/ErrorState";
import Loading from "@/components/states/Loading";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAdminTools, useSetToolEnabled, useSyncCatalog } from "@/hooks/use-admin-catalog";
import type { ToolAdminRead } from "@/types/api";

interface ToolRowProps {
  tool: ToolAdminRead;
  onToggle: (id: string, enabled: boolean) => void;
  toggling: boolean;
}

function ToolRow({ tool, onToggle, toggling }: ToolRowProps): JSX.Element {
  return (
    <TableRow>
      <TableCell className="font-medium">{tool.name}</TableCell>
      <TableCell>{tool.version}</TableCell>
      <TableCell>{tool.category}</TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <Switch
            checked={tool.enabled}
            disabled={toggling}
            aria-label={`Enable ${tool.name}`}
            onCheckedChange={(next) => onToggle(tool.id, next)}
          />
          <Badge variant={tool.enabled ? "default" : "secondary"}>
            {tool.enabled ? "Enabled" : "Disabled"}
          </Badge>
        </div>
      </TableCell>
    </TableRow>
  );
}

/** Admin screen listing every tool with an enable/disable toggle and a catalog sync action. */
export default function CatalogPage(): JSX.Element {
  const searchId = useId();
  const { data, isLoading, isError, refetch } = useAdminTools();
  const setEnabledMutation = useSetToolEnabled();
  const syncMutation = useSyncCatalog();

  const [search, setSearch] = useState("");

  const tools = useMemo(() => data ?? [], [data]);
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return tools;
    return tools.filter((tool) => tool.name.toLowerCase().includes(query));
  }, [tools, search]);

  function handleToggle(id: string, enabled: boolean): void {
    setEnabledMutation.mutate({ id, enabled });
  }

  function handleSync(): void {
    syncMutation.mutate();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Catalog</h1>
          <p className="text-sm text-muted-foreground">
            Enable or disable tools and sync the catalog from source.
          </p>
        </div>
        <Button type="button" onClick={handleSync} disabled={syncMutation.isPending}>
          Sync catalog
        </Button>
      </div>

      <div className="max-w-sm space-y-2">
        <Label htmlFor={searchId}>Search tools</Label>
        <Input
          id={searchId}
          type="search"
          placeholder="Filter by name"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </div>

      {isLoading ? (
        <Loading label="Loading tools" />
      ) : isError ? (
        <ErrorState message="Failed to load the catalog." onRetry={() => void refetch()} />
      ) : tools.length === 0 ? (
        <EmptyState
          title="No tools in the catalog"
          description="Sync the catalog to import tools from source."
        />
      ) : filtered.length === 0 ? (
        <EmptyState title="No tools match your search" description="Try a different name filter." />
      ) : (
        <div className="rounded-lg border">
          <Table>
            <caption className="sr-only">Tool catalog</caption>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Enabled</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((tool) => (
                <ToolRow
                  key={tool.id}
                  tool={tool}
                  onToggle={handleToggle}
                  toggling={setEnabledMutation.isPending}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
