import { AnimalTimeline } from "../../../../../features/animal-timeline/AnimalTimeline";

export default function AnimalTimelinePage() {
  return (
    <main>
      <h1>動物近期歷程</h1>
      <AnimalTimeline days={[]} />
    </main>
  );
}
