package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Field;

import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_2_3Test {

    @Test
    @Timeout(8000)
    void testReadReturnsCharAndUpdatesLastCharWithoutNewline() throws IOException, NoSuchFieldException, IllegalAccessException {
        Reader reader = new Reader() {
            boolean readOnce = false;

            @Override
            public int read(char[] cbuf, int off, int len) throws IOException {
                return -1;
            }

            @Override
            public int read() throws IOException {
                if (!readOnce) {
                    readOnce = true;
                    return 'a';
                }
                return -1;
            }

            @Override
            public void close() throws IOException {
            }
        };

        ExtendedBufferedReader readerUnderTest = new ExtendedBufferedReader(reader);
        int result = readerUnderTest.read();
        assertEquals('a', result);
        int lastChar = getPrivateField(readerUnderTest, "lastChar");
        int lineCounter = getPrivateField(readerUnderTest, "lineCounter");
        assertEquals('a', lastChar);
        assertEquals(0, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testReadReturnsNewlineAndIncrementsLineCounter() throws IOException, NoSuchFieldException, IllegalAccessException {
        Reader reader = new Reader() {
            boolean readOnce = false;

            @Override
            public int read(char[] cbuf, int off, int len) throws IOException {
                return -1;
            }

            @Override
            public int read() throws IOException {
                if (!readOnce) {
                    readOnce = true;
                    return '\n';
                }
                return -1;
            }

            @Override
            public void close() throws IOException {
            }
        };

        ExtendedBufferedReader readerUnderTest = new ExtendedBufferedReader(reader);
        int result = readerUnderTest.read();
        assertEquals('\n', result);
        int lastChar = getPrivateField(readerUnderTest, "lastChar");
        int lineCounter = getPrivateField(readerUnderTest, "lineCounter");
        assertEquals('\n', lastChar);
        assertEquals(1, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testReadReturnsEndOfStream() throws IOException, NoSuchFieldException, IllegalAccessException {
        Reader reader = new Reader() {
            @Override
            public int read(char[] cbuf, int off, int len) throws IOException {
                return -1;
            }

            @Override
            public int read() throws IOException {
                return -1;
            }

            @Override
            public void close() throws IOException {
            }
        };

        ExtendedBufferedReader readerUnderTest = new ExtendedBufferedReader(reader);
        int result = readerUnderTest.read();
        assertEquals(-1, result);
        int lastChar = getPrivateField(readerUnderTest, "lastChar");
        int lineCounter = getPrivateField(readerUnderTest, "lineCounter");
        assertEquals(-1, lastChar);
        assertEquals(0, lineCounter);
    }

    private int getPrivateField(Object instance, String fieldName) throws NoSuchFieldException, IllegalAccessException {
        Field field = null;
        Class<?> clazz = instance.getClass();
        while (clazz != null) {
            try {
                field = clazz.getDeclaredField(fieldName);
                break;
            } catch (NoSuchFieldException e) {
                clazz = clazz.getSuperclass();
            }
        }
        if (field == null) {
            throw new NoSuchFieldException(fieldName);
        }
        field.setAccessible(true);
        return (int) field.get(instance);
    }
}