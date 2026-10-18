export function StageHeader({ letter, title, lead }: { letter: string; title: string; lead: string }) {
  return (
    <header className="stage-header">
      <span className="stage-header__letter">{letter}</span>
      <div>
        <h1>{title}</h1>
        <p>{lead}</p>
      </div>
    </header>
  )
}
