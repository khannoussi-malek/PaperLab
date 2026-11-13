import { PackageOpen } from "lucide-react";
import { useId, useRef, useState } from "react";
import { sileo } from "sileo";
import {
  ApiError,
  packageRecordUrl,
  packageUrl,
  type Workspace,
} from "@/api/client";
import { usePackageRecord, useImportPackage } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { workspaceHref } from "@/lib/route";
import { importResultLine, packageErrorMessage } from "./packageCopy";

/** "Export package…" from a workspace's row menu: one `.paperlab` file, with its PDFs only when ticked. */
export function PackageExportDialog({
  workspace,
  onClose,
}: {
  workspace: Pick<Workspace, "id" | "name">;
  onClose: () => void;
}) {
  const [pdfs, setPdfs] = useState(false);
  const checkboxId = useId();
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Export package</DialogTitle>
          <DialogDescription>
            {workspace.name}, with its papers, tags, notes and screening record,
            in one file.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <Checkbox
              id={checkboxId}
              checked={pdfs}
              onCheckedChange={(checked) => setPdfs(checked === true)}
            />
            <Label htmlFor={checkboxId}>Include PDFs</Label>
          </div>
          <p className="text-sm text-muted-foreground">
            Without PDFs the file is small, and papers arrive as details only.
          </p>
        </div>
        <Button asChild className="self-start">
          <a href={packageUrl(workspace.id, pdfs)} download>
            Download package
          </a>
        </Button>
      </DialogContent>
    </Dialog>
  );
}

/** A link to the screening record an imported workspace carries; nothing when it has none. */
export function PackageRecordLink({ workspaceId }: { workspaceId: string }) {
  const record = usePackageRecord(workspaceId);
  if (record.data !== true) return null;
  return (
    <Button variant="ghost" size="sm" asChild>
      <a href={packageRecordUrl(workspaceId)} download>
        Screening record from the package
      </a>
    </Button>
  );
}

/** "Import package…" on the workspaces list: a hidden file input behind the button. A new workspace opens on success. */
export function ImportPackageButton() {
  const inputRef = useRef<HTMLInputElement>(null);
  const importPackage = useImportPackage();

  function importFile(file: File) {
    importPackage.mutate(file, {
      onSuccess: (result) => {
        sileo.success({ title: importResultLine(result) });
        window.location.hash = workspaceHref(result.workspace_id);
      },
      onError: (error) =>
        sileo.error({
          title: packageErrorMessage(
            error instanceof ApiError ? error.code : "",
          ),
        }),
    });
  }

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        className="justify-start text-muted-foreground"
        disabled={importPackage.isPending}
        onClick={() => inputRef.current?.click()}
      >
        <PackageOpen aria-hidden />
        {importPackage.isPending ? "Importing…" : "Import package…"}
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept=".paperlab,.zip"
        hidden
        aria-label="Package file"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) importFile(file);
        }}
      />
    </>
  );
}
