import { useId, useMemo, useState, type JSX } from "react";

import EmptyState from "@/components/states/EmptyState";
import ErrorState from "@/components/states/ErrorState";
import Loading from "@/components/states/Loading";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAdminUsers, useCreatePasswordReset, useUpdateUser } from "@/hooks/use-admin-users";
import type {
  AdminUserRead,
  AdminUserUpdate,
  PasswordResetResponse,
  UserStatus,
  UserTier,
} from "@/types/api";

const STATUSES: readonly UserStatus[] = ["pending", "active", "disabled"];
const TIERS: readonly UserTier[] = ["standard", "power"];

const STATUS_VARIANT: Record<UserStatus, BadgeProps["variant"]> = {
  pending: "secondary",
  active: "default",
  disabled: "outline",
};

/** Shared native-select styling matching the shadcn input/trigger surface. */
const SELECT_CLASS =
  "flex h-9 w-full items-center rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

function matchesQuery(user: AdminUserRead, query: string): boolean {
  return `${user.email} ${user.status}`.toLowerCase().includes(query);
}

interface StatusBadgeProps {
  status: UserStatus;
}

function StatusBadge({ status }: StatusBadgeProps): JSX.Element {
  return <Badge variant={STATUS_VARIANT[status]}>{status}</Badge>;
}

interface EditUserDialogProps {
  user: AdminUserRead;
}

function EditUserDialog({ user }: EditUserDialogProps): JSX.Element {
  const statusId = useId();
  const tierId = useId();
  const quotaId = useId();
  const updateMutation = useUpdateUser();

  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<UserStatus>(user.status);
  const [tier, setTier] = useState<UserTier>(user.tier);
  const [quota, setQuota] = useState<string>(
    user.max_concurrent_runs_override === null ? "" : String(user.max_concurrent_runs_override),
  );

  function resetForm(): void {
    setStatus(user.status);
    setTier(user.tier);
    setQuota(
      user.max_concurrent_runs_override === null ? "" : String(user.max_concurrent_runs_override),
    );
  }

  function handleOpenChange(next: boolean): void {
    if (next) resetForm();
    setOpen(next);
  }

  function buildChanges(): AdminUserUpdate {
    const changes: AdminUserUpdate = {};
    if (status !== user.status) changes.status = status;
    if (tier !== user.tier) changes.tier = tier;
    const nextQuota = quota.trim() === "" ? null : Number(quota);
    if (nextQuota !== user.max_concurrent_runs_override) {
      changes.max_concurrent_runs_override = nextQuota;
    }
    return changes;
  }

  function handleSave(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    updateMutation.mutate(
      { id: user.id, changes: buildChanges() },
      { onSuccess: () => setOpen(false) },
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" size="sm">
          Edit
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit user</DialogTitle>
          <DialogDescription>{user.email}</DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={handleSave}>
          <div className="space-y-2">
            <Label htmlFor={statusId}>Status</Label>
            <select
              id={statusId}
              className={SELECT_CLASS}
              value={status}
              onChange={(event) => setStatus(event.target.value as UserStatus)}
            >
              {STATUSES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor={tierId}>Tier</Label>
            <select
              id={tierId}
              className={SELECT_CLASS}
              value={tier}
              onChange={(event) => setTier(event.target.value as UserTier)}
            >
              {TIERS.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor={quotaId}>Max concurrent runs override</Label>
            <Input
              id={quotaId}
              type="number"
              min={0}
              placeholder="Default (no override)"
              value={quota}
              onChange={(event) => setQuota(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={updateMutation.isPending}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

interface PasswordResetDialogProps {
  reset: PasswordResetResponse | null;
  onOpenChange: (open: boolean) => void;
}

function PasswordResetDialog({ reset, onOpenChange }: PasswordResetDialogProps): JSX.Element {
  const tokenId = useId();

  async function handleCopy(): Promise<void> {
    if (reset) await navigator.clipboard.writeText(reset.token);
  }

  return (
    <Dialog open={reset !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Password reset token</DialogTitle>
          <DialogDescription>
            Shown once — copy it now and convey it to the user out of band.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor={tokenId}>Reset token</Label>
          <div className="flex gap-2">
            <Input id={tokenId} readOnly value={reset?.token ?? ""} />
            <Button type="button" variant="outline" onClick={() => void handleCopy()}>
              Copy
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface UserRowProps {
  user: AdminUserRead;
  onResetPassword: (id: string) => void;
  resetting: boolean;
}

function UserRow({ user, onResetPassword, resetting }: UserRowProps): JSX.Element {
  return (
    <TableRow>
      <TableCell className="font-medium">{user.email}</TableCell>
      <TableCell>{user.display_name}</TableCell>
      <TableCell>{user.role}</TableCell>
      <TableCell>{user.tier}</TableCell>
      <TableCell>
        <StatusBadge status={user.status} />
      </TableCell>
      <TableCell>{user.max_concurrent_runs_override ?? "—"}</TableCell>
      <TableCell>
        <div className="flex justify-end gap-2">
          <EditUserDialog user={user} />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onResetPassword(user.id)}
            disabled={resetting}
          >
            Reset password
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

/** Admin screen listing users with search, an edit dialog, and password reset. */
export default function UsersPage(): JSX.Element {
  const searchId = useId();
  const { data, isLoading, isError, refetch } = useAdminUsers();
  const resetMutation = useCreatePasswordReset();

  const [query, setQuery] = useState("");
  const [reset, setReset] = useState<PasswordResetResponse | null>(null);

  const filtered = useMemo(() => {
    const users = data ?? [];
    const normalized = query.trim().toLowerCase();
    return normalized ? users.filter((user) => matchesQuery(user, normalized)) : users;
  }, [data, query]);

  function handleResetPassword(id: string): void {
    resetMutation.mutate(id, { onSuccess: (response) => setReset(response) });
  }

  function handleResetDialogChange(open: boolean): void {
    if (!open) setReset(null);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
        <p className="text-sm text-muted-foreground">Manage user access, tiers, and quotas.</p>
      </div>

      <div className="max-w-sm space-y-2">
        <Label htmlFor={searchId}>Search users</Label>
        <Input
          id={searchId}
          type="search"
          placeholder="Filter by email or status"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      {isLoading ? (
        <Loading label="Loading users" />
      ) : isError ? (
        <ErrorState message="Failed to load users." onRetry={() => void refetch()} />
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No users found"
          description="Nothing matches your search. Try a different term."
        />
      ) : (
        <div className="rounded-lg border">
          <Table>
            <caption className="sr-only">Users</caption>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Tier</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Quota override</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((user) => (
                <UserRow
                  key={user.id}
                  user={user}
                  onResetPassword={handleResetPassword}
                  resetting={resetMutation.isPending}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <PasswordResetDialog reset={reset} onOpenChange={handleResetDialogChange} />
    </div>
  );
}
