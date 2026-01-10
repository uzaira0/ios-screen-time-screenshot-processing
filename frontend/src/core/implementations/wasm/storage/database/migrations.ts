import type { ScreenshotDB } from './ScreenshotDB';

export async function runMigrations(db: ScreenshotDB): Promise<void> {
  db.on('populate', async () => {
    console.log('Database created for the first time');

    await db.settings.add({
      key: 'initialized',
      value: true,
      updatedAt: new Date().toISOString()
    });

    await db.settings.add({
      key: 'version',
      value: '1.0.0',
      updatedAt: new Date().toISOString()
    });
  });

  db.on('versionchange', (event) => {
    console.log('Database version changed:', event);

    if (event.oldVersion < 1) {
      console.log('Migrating to version 1...');
    }

    if (event.oldVersion < 2) {
      console.log('Migrating to version 2... Adding compound indexes');
    }
  });
}

export async function clearDatabase(db: ScreenshotDB): Promise<void> {
  await db.transaction('rw', [db.screenshots, db.annotations, db.imageBlobs, db.processingQueue, db.groups, db.syncRecords, db.settings], async () => {
    await Promise.all([
      db.screenshots.clear(),
      db.annotations.clear(),
      db.imageBlobs.clear(),
      db.processingQueue.clear(),
      db.groups.clear(),
      db.syncRecords.clear(),
      db.settings.clear(),
    ]);
  });
}

export async function exportDatabaseInfo(db: ScreenshotDB): Promise<{
  name: string;
  version: number;
  tableStats: { name: string; count: number }[];
}> {
  const tables = ['screenshots', 'annotations', 'imageBlobs', 'settings', 'processingQueue', 'groups', 'syncRecords'] as const;

  const tableStats = await Promise.all(
    tables.map(async (tableName) => ({
      name: tableName,
      count: await db.table(tableName).count()
    }))
  );

  return {
    name: db.name,
    version: db.verno,
    tableStats
  };
}
