// Sample TypeScript file for testing code chunking

export interface User {
    id: string;
    name: string;
    email: string;
}

export function greetUser(user: User): string {
    return `Hello, ${user.name}!`;
}

export class UserService {
    private users: User[] = [];

    addUser(user: User): void {
        this.users.push(user);
    }

    findUser(id: string): User | undefined {
        return this.users.find(u => u.id === id);
    }
}
