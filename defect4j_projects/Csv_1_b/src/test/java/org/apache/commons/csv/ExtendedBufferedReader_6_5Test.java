package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Field;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class ExtendedBufferedReader_6_5Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testLookAheadReturnsChar() throws IOException {
        ExtendedBufferedReader spyReader = Mockito.spy(extendedBufferedReader);

        // Use reflection to set lastChar to UNDEFINED to avoid interference
        setLastChar(spyReader, ExtendedBufferedReader.UNDEFINED);

        // mock read() call to return 'A' (65)
        doReturn(65).when(spyReader).read();

        // Since mark and reset are final in BufferedReader, do not stub them, let real methods run

        int result = spyReader.lookAhead();

        verify(spyReader).read();

        assertEquals(65, result);
    }

    @Test
    @Timeout(8000)
    void testLookAheadReturnsEndOfStream() throws IOException {
        ExtendedBufferedReader spyReader = Mockito.spy(extendedBufferedReader);

        setLastChar(spyReader, ExtendedBufferedReader.UNDEFINED);

        doReturn(ExtendedBufferedReader.END_OF_STREAM).when(spyReader).read();

        int result = spyReader.lookAhead();

        verify(spyReader).read();

        assertEquals(ExtendedBufferedReader.END_OF_STREAM, result);
    }

    @Test
    @Timeout(8000)
    void testLookAheadThrowsIOException() throws IOException {
        ExtendedBufferedReader spyReader = Mockito.spy(extendedBufferedReader);

        // Use doThrow to throw IOException when mark is called
        doThrow(new IOException("mark exception")).when(spyReader).mark(anyInt());

        IOException thrown = assertThrows(IOException.class, () -> spyReader.lookAhead());
        assertEquals("mark exception", thrown.getMessage());
    }

    private void setLastChar(ExtendedBufferedReader reader, int value) {
        try {
            Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
            lastCharField.setAccessible(true);
            lastCharField.setInt(reader, value);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }
}