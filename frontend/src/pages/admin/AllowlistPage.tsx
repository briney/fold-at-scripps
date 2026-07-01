import { useId, useState, type FormEvent, type JSX } from "react";

import EmptyState from "@/components/states/EmptyState";
import ErrorState from "@/components/states/ErrorState";
import Loading from "@/components/states/Loading";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
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
import {
  useAddAllowedEmail,
  useAllowedEmails,
  useRemoveAllowedEmail,
} from "@/hooks/use-admin-access";
import type { AllowedEmailRead } from "@/types/api";

/** Format an ISO timestamp for display, falling back to the raw string. */
function formatCreatedAt(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

interface RemoveEmailDialogProps {
  entry: AllowedEmailRead;
  onConfirm: (id: string) => void;
  removing: boolean;
}

function RemoveEmailDialog({ entry, onConfirm, removing }: RemoveEmailDialogProps): JSX.Element {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button type="button" variant="ghost" size="sm" disabled={removing}>
          Remove
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove email from allowlist?</AlertDialogTitle>
          <AlertDialogDescription>
            {entry.email} will no longer be permitted to register. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={() => onConfirm(entry.id)}>Remove</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

interface AllowedEmailRowProps {
  entry: AllowedEmailRead;
  onRemove: (id: string) => void;
  removing: boolean;
}

function AllowedEmailRow({ entry, onRemove, removing }: AllowedEmailRowProps): JSX.Element {
  return (
    <TableRow>
      <TableCell className="font-medium">{entry.email}</TableCell>
      <TableCell>{formatCreatedAt(entry.created_at)}</TableCell>
      <TableCell>
        <div className="flex justify-end">
          <RemoveEmailDialog entry={entry} onConfirm={onRemove} removing={removing} />
        </div>
      </TableCell>
    </TableRow>
  );
}

/** Admin screen listing allowlisted emails with add and per-row remove actions. */
export default function AllowlistPage(): JSX.Element {
  const emailId = useId();
  const { data, isLoading, isError, refetch } = useAllowedEmails();
  const addMutation = useAddAllowedEmail();
  const removeMutation = useRemoveAllowedEmail();

  const [email, setEmail] = useState("");

  function handleAdd(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) return;
    addMutation.mutate(trimmed, { onSuccess: () => setEmail("") });
  }

  function handleRemove(id: string): void {
    removeMutation.mutate(id);
  }

  const entries = data ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Allowlist</h1>
        <p className="text-sm text-muted-foreground">
          Control which email addresses are permitted to register.
        </p>
      </div>

      <form className="flex max-w-md items-end gap-2" onSubmit={handleAdd}>
        <div className="flex-1 space-y-2">
          <Label htmlFor={emailId}>Add email</Label>
          <Input
            id={emailId}
            type="email"
            placeholder="user@scripps.edu"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <Button type="submit" disabled={addMutation.isPending || email.trim() === ""}>
          Add
        </Button>
      </form>

      {isLoading ? (
        <Loading label="Loading allowlist" />
      ) : isError ? (
        <ErrorState message="Failed to load the allowlist." onRetry={() => void refetch()} />
      ) : entries.length === 0 ? (
        <EmptyState
          title="No allowlisted emails"
          description="Add an email above to permit a new user to register."
        />
      ) : (
        <div className="rounded-lg border">
          <Table>
            <caption className="sr-only">Allowlisted emails</caption>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Added</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry) => (
                <AllowedEmailRow
                  key={entry.id}
                  entry={entry}
                  onRemove={handleRemove}
                  removing={removeMutation.isPending}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
