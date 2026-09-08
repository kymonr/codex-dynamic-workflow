"""Prepare an isolated five-node v4 example. No model calls or account access."""
from pathlib import Path
import argparse
import json


def prepare(output: Path) -> Path:
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    fixture = Path(__file__).resolve().parents[1] / 'tests/fixtures/invoice.py'
    content = fixture.read_bytes()
    source = output / 'source'; source.mkdir()
    (source / 'invoice.py').write_bytes(content)
    base = dict(sources=['invoice.py'], checks=['inspect'], risk='low')
    nodes = [dict(base, id='main', role='explorer', risk='high',
                  task='Astra: inspect fixture behavior and retain complete mainline coverage.'),
             dict(base, id='review', role='reviewer', verifies='main', depends=['main'],
                  task='Astra: independently verify the mainline result against original fixture bytes.')]
    for name, question in [('coverage','Find omitted input paths.'),
                           ('counterexample','Find a concrete counterexample.'),
                           ('test_gaps','Find missing tests or an alternative explanation.')]:
        snapshot = output / ('snapshot-' + name); snapshot.mkdir()
        (snapshot / 'invoice.py').write_bytes(content)
        nodes.append(dict(base, id=name, role='explorer', task=question,
                          supplemental=True, required=False, ordinary_qualified=True,
                          snapshot_root=str(snapshot)))
    plan = dict(root=str(source), goal='Readonly Astra mainline plus three optional Luna probes',
                backend='native', workflow='astra-mainline', nodes=nodes)
    path = output / 'plan.json'
    path.write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(prepare(parser.parse_args().output))
