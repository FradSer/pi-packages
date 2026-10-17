from pathlib import Path
import subprocess


def test_internal_runtime_properties_do_not_require_a_public_type_surface(tmp_path: Path) -> None:
    # Counterexample to the actual failed proposal's universal description.
    # A public member check says nothing about exposing incidental properties.
    source = tmp_path / 'public-contract.ts'
    source.write_text('''type PublicContract = (() => number) & { visible: boolean };
export function create(): PublicContract {
  return Object.assign(() => 1, { visible: true, internalDiagnostic: () => 'private detail' });
}
declare function expectType<T>(value: T): void;
expectType<number>(create()());
expectType<boolean>(create().visible);
''')
    result = subprocess.run(
        ['pnpm', 'exec', 'tsc', '--noEmit', '--strict', '--skipLibCheck', '--target', 'ES2022',
         '--module', 'NodeNext', '--moduleResolution', 'NodeNext', str(source)],
        capture_output=True, text=True, timeout=40, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
