import React, { useEffect, useState } from 'react';
import { GroupCard } from './GroupCard';
import { db } from '@/core/implementations/wasm/storage/database';
import type { Group } from '@/core/models';

interface GroupListProps {
  onRefresh?: () => void;
}

export const GroupList: React.FC<GroupListProps> = ({ onRefresh }) => {
  const [groups, setGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);

  const loadGroups = async () => {
    try {
      setLoading(true);
      const allGroups = await db.groups.orderBy('created_at').reverse().toArray();
      setGroups(allGroups);
    } catch (error) {
      console.error('Failed to load groups:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadGroups();
  }, []);

  // Expose refresh function
  useEffect(() => {
    if (onRefresh) {
      // Allow parent to trigger refresh
    }
  }, [onRefresh]);

  if (loading) {
    return (
      <div className="text-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
        <p className="text-gray-500 mt-2">Loading groups...</p>
      </div>
    );
  }

  if (groups.length === 0) {
    return (
      <div className="text-center py-12 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
        <div className="text-4xl mb-4">📁</div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">No Groups Yet</h3>
        <p className="text-gray-600 max-w-md mx-auto">
          Groups are automatically created when screenshots are uploaded via the API.
          You can also upload screenshots manually below.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {groups.map((group) => (
        <GroupCard key={group.id} group={group} />
      ))}
    </div>
  );
};
